"""Free-first observed PIT ingress core (FREE_FIRST_OBSERVED_PIT_INGRESS_CORE_V1).

The single, source-neutral, offline and deterministic seam between externally captured native market observations and
the accepted ``HistoricalPitDataset``. It performs no IO of any kind: the caller supplies immutable, already captured
observations as typed records of exact decimal text, together with an explicit provenance declaration. Nothing here
fetches, subscribes, downloads, schedules or reads a clock.

What it enforces:

* provenance - every observation names a declared source object (identity, asserted SHA-256, byte length) of one
  declared source (identity, contract reference, rights status and rights reference); every declared object must be
  used; the authenticated EF-3 manifest must be re-proven, anchored, correlated and bound to the expected registry, and
  each mapped series must carry exactly the source reference, rights and instrument coverage the ingress declares;
* implemented semantics - each stream maps into exactly one EF-3 series whose registry-derived semantics are EXACTLY
  the named policies this module implements (``observed_pit_implemented_series_semantics``). The order book stays
  ``l2`` / depth 50 / ``strict_monotonic`` / ``snapshot_then_delta`` / ``sequence_gap_reject``; any other declaration,
  an L1 one included, is refused rather than mapped;
* native book continuity under the one code-defined profile ``update_id_predecessor_chain_snapshot_aligned.v1``:
  deltas received before a snapshot are buffered; at the snapshot, deltas whose native final update id precedes the
  snapshot's ``last_update_id`` are dropped and the first applied delta must straddle it; every later delta must name
  the previous applied delta as its native predecessor; a predecessor mismatch invalidates the book until a disconnect
  marker and a new snapshot; a snapshot without a preceding disconnect, a regression, a replay, a malformed native id
  triple, a crossed book or an invalid level rejects the whole ingress. Native update ids are taken from the source,
  never generated: the book record identity IS the native final update id;
* genuine depth - a book state is admitted only with at least 50 bid and 50 ask levels whose 50th level lies inside the
  anchoring snapshot's price horizon (levels beyond it are unknown, never assumed empty);
* time - source event time, provider receipt time and finality stay separate inputs. A record is never available
  before its own receipt, and a buffered delta never before the snapshot that anchored it. Funding uses the governed
  window-open event time, the observed publication instant as availability and the settlement instant as finality, so
  an ex-post final rate is never visible before it was actually observed; an interval is a governed input, never an
  assumed eight hours;
* the accepted PIT authority - records are built and the dataset assembled ONLY by the public
  ``build_historical_pit_record`` / ``build_historical_pit_dataset``; there is no second dataset, decision or
  economics authority here.

What it does NOT prove (structural non-claims): that the source is authentic, that the observations derive from the
declared objects' bytes (digests are asserted, never verified here), that the archive is complete, that the continuity
profile is qualified against a real provider, that receipt times are machine-proven, venue facts, or any real paper
data, readiness or Stage-4 evidence. The continuity profile is documented and NOT qualified, so every READY ingress
carries ``NEEDS_EXTERNAL_FACTS`` and never advances. Malformed caller input raises ``ObservedPitIngressError``; an
integrity defect in the supplied observations, provenance or upstream authority yields ``REJECTED``/``NOT_EVALUATED``.
One assembly path serves the builder and the verifier; ``verify_observed_pit_ingress`` is total.
"""

from __future__ import annotations

import json
from bisect import bisect_left, insort
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.data.requirements import DataRequirementKey
from crypto_core.strategy.source_packet import SourcePacketRightsStatus
from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    build_edge_authority_binding,
    edge_authority_binding_snapshot,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    resolve_edge_gate_verdict,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSeriesFinality,
    EdgeSeriesRevisionPolicy,
    EdgeSourcePacketEvidence,
    EdgeSourceSeriesRecord,
    edge_source_packet_evidence_from_payload,
    edge_source_packet_evidence_payload_is_well_formed,
    edge_source_packet_evidence_to_dict,
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
    HistoricalPitRecord,
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
    is_canonical_pit_decimal,
)

_SCHEMA_VERSION = "observed-pit-ingress-evidence.v1"
_REASON_PREFIX = "observed_pit_ingress"
_SELF_DIGEST_FIELD = "ingress_digest"
_MAX_WIRE_INT = 9223372036854775807
_MAX_TEXT_LENGTH = 512
_INSTRUMENT_EXTRA_CHARS = frozenset("-_./:")
_DATASET_SOURCE_REFERENCE_PREFIX = "observed-pit-ingress-declaration:"

OBSERVED_PIT_INGRESS_CONTRACT_ID = "FREE_FIRST_OBSERVED_PIT_INGRESS_CORE_V1"
OBSERVED_PIT_BOOK_DEPTH = 50
OBSERVED_PIT_CONTINUITY_PROFILE_ID = "update_id_predecessor_chain_snapshot_aligned.v1"

# The one code-defined continuity profile. Its documentary basis is a provider procedure that has NOT been qualified
# against real captured bytes, so the profile is non-authoritative: it governs this module's checks, never source truth.
_CONTINUITY_PROFILE: dict[str, str] = {
    "profile_id": OBSERVED_PIT_CONTINUITY_PROFILE_ID,
    "snapshot_anchor": "snapshot_last_update_id",
    "buffer_rule": "deltas_received_before_the_snapshot_since_the_last_disconnect_are_buffered",
    "stale_rule": "drop_delta_when_final_update_id_lt_anchor",
    "alignment_rule": "first_applied_first_update_id_le_anchor_le_final_update_id",
    "chain_rule": "previous_final_update_id_eq_prior_applied_final_update_id",
    "delta_id_rule": "previous_final_update_id_lt_first_update_id_le_final_update_id",
    "regression_rule": "final_update_id_le_prior_applied_rejects",
    "gap_rule": "predecessor_mismatch_invalidates_until_disconnect_then_snapshot",
    "resync_rule": "snapshot_only_at_input_start_or_after_disconnect",
    "quantity_rule": "absolute_quantity_zero_removes_absent_removal_is_noop",
    "availability_rule": "max_of_delta_receipt_and_anchoring_snapshot_receipt",
    "depth_rule": "fifty_levels_each_side_inside_the_snapshot_horizon",
    "documentary_basis": "binance_usdm_local_order_book_procedure",
    "qualification_status": "documented_not_qualified",
}
_CONTINUITY_PROFILE_QUALIFIED = False

_ORDER_BOOK_KEY = DataRequirementKey.ORDER_BOOK.value
_MARK_KEY = DataRequirementKey.MARK_PRICE.value
_FUNDING_KEY = DataRequirementKey.FUNDING_RATE.value

# Exactly the registry-derived EF-3 series semantics this module implements, per data requirement key.
_IMPLEMENTED_SERIES_SEMANTICS: dict[str, dict[str, object]] = {
    _ORDER_BOOK_KEY: {
        "historical_source": "order_book_snapshot_delta_v1",
        "event_time_policy": "book_event_ns",
        "available_at_policy": "book_available_ns",
        "finalized_at_policy": "book_sequence_finalized_ns",
        "funding_semantics": None,
        "price_semantics": None,
        "order_book_level": "l2",
        "order_book_depth": OBSERVED_PIT_BOOK_DEPTH,
        "sequence_policy": "strict_monotonic",
        "resync_policy": "snapshot_then_delta",
        "finality_policy": "sequence_gap_reject",
    },
    _MARK_KEY: {
        "historical_source": "mark_price_history_v1",
        "event_time_policy": "mark_event_ns",
        "available_at_policy": "mark_available_ns",
        "finalized_at_policy": "mark_finalized_ns",
        "funding_semantics": None,
        "price_semantics": "mark_price",
        "order_book_level": None,
        "order_book_depth": None,
        "sequence_policy": None,
        "resync_policy": None,
        "finality_policy": "mark_snapshot_final",
    },
    _FUNDING_KEY: {
        "historical_source": "funding_history_v1",
        "event_time_policy": "funding_window_open_ns",
        "available_at_policy": "funding_published_ns",
        "finalized_at_policy": "funding_finalized_ns",
        "funding_semantics": "final",
        "price_semantics": None,
        "order_book_level": None,
        "order_book_depth": None,
        "sequence_policy": None,
        "resync_policy": None,
        "finality_policy": "funding_cycle_closed",
    },
}

# PIT record identities, stated so that no generated identity is ever presented as a native exchange sequence.
_BOOK_SEQUENCE_IDENTITY = "native_final_update_id"
_MARK_SEQUENCE_IDENTITY = "source_event_time_ns_not_a_native_sequence"
_FUNDING_SEQUENCE_IDENTITY = "governed_settlement_grid_index_not_a_native_sequence"

OBSERVED_PIT_INGRESS_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("edge_proven", False),
    ("profitability_proven", False),
    ("candidate_admitted_to_paper", False),
    ("operational_readiness", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("deribit_ready", False),
    ("private_api_ready", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("real_capital_reserved", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
    ("network_io_performed", False),
    ("filesystem_io_performed", False),
    ("source_authenticity_proven", False),
    ("source_object_bytes_verified", False),
    ("observation_derivation_proven", False),
    ("continuity_profile_qualified", False),
    ("receipt_time_machine_proven", False),
    ("timestamp_origin_proven", False),
    ("archive_completeness_proven", False),
    ("external_archive_truth_proven", False),
    ("venue_facts_proven", False),
    ("real_paper_data", False),
    ("real_paper_execution_authorized", False),
    ("stage4_evidence", False),
)


class ObservedPitIngressError(EdgeArtifactError):
    """Malformed caller input or a non-serializable upstream object: an invalid ingress is never represented."""


# --- caller inputs ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservedSourceObject:
    """One immutable externally captured source object. Its identity and SHA-256 are ASSERTED, never verified here."""

    object_id: str
    content_sha256: str
    byte_length: int


@dataclass(frozen=True)
class ObservedSourceDeclaration:
    """The one declared source of an ingress: identity, contract reference, rights and its immutable objects."""

    source_id: str
    source_contract_reference: str
    rights_status: SourcePacketRightsStatus
    rights_reference: str
    objects: tuple[ObservedSourceObject, ...]


@dataclass(frozen=True)
class ObservedBookLevel:
    """One native price level: exact canonical decimal text; a delta quantity is absolute (zero removes)."""

    price: str
    quantity: str


@dataclass(frozen=True)
class ObservedBookSnapshot:
    """A native full-depth snapshot anchored on its native ``last_update_id``."""

    object_id: str
    receipt_ns: int
    event_time_ns: int
    last_update_id: int
    bids: tuple[ObservedBookLevel, ...]
    asks: tuple[ObservedBookLevel, ...]


@dataclass(frozen=True)
class ObservedBookDelta:
    """A native diff event: first/final update ids and the native final update id of its predecessor event."""

    object_id: str
    receipt_ns: int
    event_time_ns: int
    first_update_id: int
    final_update_id: int
    previous_final_update_id: int
    bids: tuple[ObservedBookLevel, ...]
    asks: tuple[ObservedBookLevel, ...]


@dataclass(frozen=True)
class ObservedDisconnect:
    """A positional connection-break marker of the capture; it carries no time because a capture may record none."""

    object_id: str


ObservedBookEvent = ObservedBookSnapshot | ObservedBookDelta | ObservedDisconnect


@dataclass(frozen=True)
class ObservedBookStream:
    series_id: str
    source_reference: str
    continuity_profile_id: str
    events: tuple[ObservedBookEvent, ...]


@dataclass(frozen=True)
class ObservedMarkObservation:
    object_id: str
    receipt_ns: int
    event_time_ns: int
    mark_price: str


@dataclass(frozen=True)
class ObservedMarkStream:
    series_id: str
    source_reference: str
    observations: tuple[ObservedMarkObservation, ...]


@dataclass(frozen=True)
class ObservedFundingSettlement:
    """One FINAL historical settlement: its source identity, settlement instant and the observed publication of it."""

    object_id: str
    settlement_id: str
    settlement_time_ns: int
    funding_rate: str
    published_object_id: str
    published_observed_at_ns: int


@dataclass(frozen=True)
class ObservedFundingStream:
    """Final settlements over a declared coverage window on an externally governed settlement interval."""

    series_id: str
    source_reference: str
    governed_interval_ns: int
    interval_reference: str
    coverage_start_ns: int
    coverage_end_ns: int
    settlements: tuple[ObservedFundingSettlement, ...]


@dataclass(frozen=True)
class ObservedPitIngressInputs:
    """Everything one ingress consumes; consumers re-prove an evidence by rebuilding it from exactly these."""

    ingress_id: str
    correlation_id: str
    dataset_id: str
    instrument: str
    declaration: ObservedSourceDeclaration
    source_manifest: EdgeSourcePacketEvidence
    expected_source_manifest_digest: str
    expected_data_requirement_registry_digest: str
    book: ObservedBookStream
    mark: ObservedMarkStream
    funding: ObservedFundingStream


# --- outputs ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservedBookSegment:
    """One snapshot-anchored continuity segment of the book stream and exactly what it admitted."""

    anchor_last_update_id: int
    anchor_receipt_ns: int
    first_applied_final_update_id: int | None
    last_applied_final_update_id: int | None
    applied_delta_count: int
    emitted_record_count: int
    stale_delta_count: int
    reobserved_state_count: int
    depth_ineligible_count: int
    horizon_ineligible_count: int
    end_reason: str


@dataclass(frozen=True)
class ObservedPitIngressEvidence:
    """Digest-bound provenance, continuity and coverage evidence of one ingress. Paper-only; proves no source truth."""

    schema_version: str
    contract_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    ingress_id: str
    correlation_id: str
    dataset_id: str
    instrument: str
    source_id: str
    source_contract_reference: str
    rights_status: str
    rights_reference: str
    source_objects: tuple[ObservedSourceObject, ...]
    declaration_digest: str
    observation_digest: str
    source_manifest_digest: str
    data_requirement_registry_digest: str
    continuity_profile_id: str
    continuity_profile_digest: str
    book_series_id: str
    mark_series_id: str
    funding_series_id: str
    book_sequence_identity: str
    mark_sequence_identity: str
    funding_sequence_identity: str
    book_segments: tuple[ObservedBookSegment, ...]
    book_disconnect_count: int
    book_gap_count: int
    book_unanchored_delta_count: int
    book_invalidated_delta_count: int
    book_record_count: int
    mark_record_count: int
    funding_record_count: int
    funding_interval_ns: int
    funding_interval_reference: str
    funding_coverage_start_ns: int
    funding_coverage_end_ns: int
    dataset_digest: str
    dataset_status: str
    dataset_gate_verdict: str
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    ingress_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
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
    network_io_performed: bool = False
    filesystem_io_performed: bool = False
    source_authenticity_proven: bool = False
    source_object_bytes_verified: bool = False
    observation_derivation_proven: bool = False
    continuity_profile_qualified: bool = False
    receipt_time_machine_proven: bool = False
    timestamp_origin_proven: bool = False
    archive_completeness_proven: bool = False
    external_archive_truth_proven: bool = False
    venue_facts_proven: bool = False
    real_paper_data: bool = False
    real_paper_execution_authorized: bool = False
    stage4_evidence: bool = False


@dataclass(frozen=True)
class ObservedPitIngressResult:
    """The evidence and, only when that dataset is READY, the accepted dataset it assembled."""

    evidence: ObservedPitIngressEvidence
    dataset: HistoricalPitDataset | None


# --- strict helpers ---------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> ObservedPitIngressError:
    return ObservedPitIngressError(_reason(code))


def _sorted_unique(reasons: list[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT_LENGTH
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
        raise _fail("instrument_invalid")
    if any(not (char.isascii() and (char.isalnum() or char in _INSTRUMENT_EXTRA_CHARS)) for char in value):
        raise _fail("instrument_invalid")
    return _require_text(value, "instrument")


def _require_time(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0 or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    return value


def _require_native_id(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    return value


def _require_decimal(value: object, field_name: str) -> Fraction:
    if not is_canonical_pit_decimal(value):
        raise _fail(f"{field_name}_noncanonical")
    return Fraction(value)  # type: ignore[arg-type]


def _require_tuple(value: object, field_name: str, *, allow_empty: bool) -> tuple[object, ...]:
    if type(value) is not tuple or (not value and not allow_empty):
        raise _fail(f"{field_name}_invalid")
    return value


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


def _typed_identical(left: object, right: object) -> bool:
    """Exact-type structural identity: Python equality is never a trust decision (False/0, str-Enum aliases)."""

    if type(left) is not type(right):
        return False
    if is_dataclass(left) and not isinstance(left, type):
        return all(_typed_identical(getattr(left, item.name), getattr(right, item.name)) for item in fields(left))
    if type(left) is tuple:
        return len(left) == len(right) and all(  # type: ignore[arg-type]
            _typed_identical(a, b)
            for a, b in zip(left, right, strict=True)  # type: ignore[call-overload]
        )
    return left == right


# --- canonical caller input -------------------------------------------------------------------------------------------


def _canonical_declaration(declaration: object) -> ObservedSourceDeclaration:
    if type(declaration) is not ObservedSourceDeclaration:
        raise _fail("declaration_malformed")
    if type(declaration.rights_status) is not SourcePacketRightsStatus:
        raise _fail("declaration_rights_status_invalid")
    objects: dict[str, ObservedSourceObject] = {}
    for item in _require_tuple(declaration.objects, "declaration_objects", allow_empty=False):
        if type(item) is not ObservedSourceObject:
            raise _fail("source_object_malformed")
        object_id = _require_token(item.object_id, "source_object_id")
        if not edge_is_hex64(item.content_sha256):
            raise _fail("source_object_sha256_invalid")
        if object_id in objects:
            raise _fail("source_object_id_duplicate")
        objects[object_id] = ObservedSourceObject(
            object_id=object_id,
            content_sha256=item.content_sha256,
            byte_length=_require_time(item.byte_length, "source_object_byte_length"),
        )
    return ObservedSourceDeclaration(
        source_id=_require_token(declaration.source_id, "source_id"),
        source_contract_reference=_require_text(declaration.source_contract_reference, "source_contract_reference"),
        rights_status=declaration.rights_status,
        rights_reference=_require_text(declaration.rights_reference, "rights_reference"),
        objects=tuple(objects[key] for key in sorted(objects)),
    )


def _canonical_levels(value: object, field_name: str) -> tuple[tuple[Fraction, str, Fraction, str], ...]:
    levels = []
    for item in _require_tuple(value, field_name, allow_empty=True):
        if type(item) is not ObservedBookLevel:
            raise _fail(f"{field_name}_level_malformed")
        price = _require_decimal(item.price, f"{field_name}_price")
        quantity = _require_decimal(item.quantity, f"{field_name}_quantity")
        levels.append((price, item.price, quantity, item.quantity))
    return tuple(levels)


def _canonical_book_event(event: object) -> None:
    if type(event) is ObservedDisconnect:
        _require_token(event.object_id, "book_object_id")
        return
    if type(event) is ObservedBookSnapshot:
        _require_native_id(event.last_update_id, "snapshot_last_update_id")
    elif type(event) is ObservedBookDelta:
        _require_native_id(event.first_update_id, "delta_first_update_id")
        _require_native_id(event.final_update_id, "delta_final_update_id")
        _require_native_id(event.previous_final_update_id, "delta_previous_final_update_id")
    else:
        raise _fail("book_event_malformed")
    _require_token(event.object_id, "book_object_id")
    _require_time(event.receipt_ns, "book_receipt_ns")
    _require_time(event.event_time_ns, "book_event_time_ns")
    _canonical_levels(event.bids, "book_bids")
    _canonical_levels(event.asks, "book_asks")


def _canonical_book_stream(stream: object) -> ObservedBookStream:
    if type(stream) is not ObservedBookStream:
        raise _fail("book_stream_malformed")
    if stream.continuity_profile_id != OBSERVED_PIT_CONTINUITY_PROFILE_ID:
        raise _fail("book_continuity_profile_unknown")
    for event in _require_tuple(stream.events, "book_events", allow_empty=False):
        _canonical_book_event(event)
    return ObservedBookStream(
        series_id=_require_token(stream.series_id, "book_series_id"),
        source_reference=_require_text(stream.source_reference, "book_source_reference"),
        continuity_profile_id=stream.continuity_profile_id,
        events=stream.events,
    )


def _canonical_mark_stream(stream: object) -> ObservedMarkStream:
    if type(stream) is not ObservedMarkStream:
        raise _fail("mark_stream_malformed")
    for item in _require_tuple(stream.observations, "mark_observations", allow_empty=False):
        if type(item) is not ObservedMarkObservation:
            raise _fail("mark_observation_malformed")
        _require_token(item.object_id, "mark_object_id")
        _require_time(item.receipt_ns, "mark_receipt_ns")
        _require_time(item.event_time_ns, "mark_event_time_ns")
        _require_decimal(item.mark_price, "mark_price")
    return ObservedMarkStream(
        series_id=_require_token(stream.series_id, "mark_series_id"),
        source_reference=_require_text(stream.source_reference, "mark_source_reference"),
        observations=stream.observations,
    )


def _canonical_funding_stream(stream: object) -> ObservedFundingStream:
    if type(stream) is not ObservedFundingStream:
        raise _fail("funding_stream_malformed")
    for item in _require_tuple(stream.settlements, "funding_settlements", allow_empty=False):
        if type(item) is not ObservedFundingSettlement:
            raise _fail("funding_settlement_malformed")
        _require_token(item.object_id, "funding_object_id")
        _require_token(item.settlement_id, "funding_settlement_id")
        _require_time(item.settlement_time_ns, "funding_settlement_time_ns")
        _require_decimal(item.funding_rate, "funding_rate")
        _require_token(item.published_object_id, "funding_published_object_id")
        _require_time(item.published_observed_at_ns, "funding_published_observed_at_ns")
    start = _require_time(stream.coverage_start_ns, "funding_coverage_start_ns")
    end = _require_time(stream.coverage_end_ns, "funding_coverage_end_ns")
    if end <= start:
        raise _fail("funding_coverage_window_invalid")
    return ObservedFundingStream(
        series_id=_require_token(stream.series_id, "funding_series_id"),
        source_reference=_require_text(stream.source_reference, "funding_source_reference"),
        governed_interval_ns=_require_time(stream.governed_interval_ns, "funding_governed_interval_ns"),
        interval_reference=_require_text(stream.interval_reference, "funding_interval_reference"),
        coverage_start_ns=start,
        coverage_end_ns=end,
        settlements=stream.settlements,
    )


# --- upstream authority -----------------------------------------------------------------------------------------------


def _manifest_codes(
    manifest: EdgeSourcePacketEvidence, *, anchor: str, correlation_id: str, registry_digest: str
) -> list[str]:
    verification = verify_edge_source_packet_evidence(manifest)
    if not verification.intact:
        return [_reason(f"source_manifest_integrity_failure:{code}") for code in verification.reason_codes]
    if verification.recomputed_digest != anchor:
        return [_reason("source_manifest_digest_mismatch")]
    if manifest.correlation_id != correlation_id:
        return [_reason("source_manifest_correlation_mismatch")]
    if manifest.status is not EdgeEvidenceStatus.READY:
        return [_reason("source_manifest_rejected")]
    if manifest.data_requirement_registry_digest != registry_digest:
        return [_reason("data_requirement_registry_mismatch")]
    return []


def _series_codes(
    manifest: EdgeSourcePacketEvidence,
    *,
    series_id: str,
    source_reference: str,
    key: str,
    instrument: str,
    declaration: ObservedSourceDeclaration,
) -> list[str]:
    matches: list[EdgeSourceSeriesRecord] = [item for item in manifest.series if item.series_id == series_id]
    if len(matches) != 1:
        return [_reason(f"manifest_series_missing:{series_id}")]
    series = matches[0]
    codes: list[str] = []

    def mismatch(field_name: str) -> None:
        codes.append(_reason(f"manifest_series_semantics_mismatch:{series_id}:{field_name}"))

    if series.data_requirement_key != key:
        return [_reason(f"manifest_series_semantics_mismatch:{series_id}:data_requirement_key")]
    if series.registry_requirement_bound is not True:
        mismatch("registry_requirement_bound")
    for field_name, expected in _IMPLEMENTED_SERIES_SEMANTICS[key].items():
        actual = getattr(series, field_name)
        if type(actual) is not type(expected) or actual != expected:
            mismatch(field_name)
    if series.paper_parity_available is not True:
        mismatch("paper_parity_available")
    if series.finality != EdgeSeriesFinality.FINALIZED_ONLY.value or series.finalized_only is not True:
        mismatch("finality")
    if (
        series.revision_policy != EdgeSeriesRevisionPolicy.IMMUTABLE_AFTER_FINALIZATION.value
        or series.point_in_time_revision_safe is not True
    ):
        mismatch("revision_policy")
    if series.source_reference != source_reference:
        codes.append(_reason(f"manifest_series_source_reference_mismatch:{series_id}"))
    rights = (series.rights_status, series.rights_reference)
    if rights != (declaration.rights_status.value, declaration.rights_reference):
        codes.append(_reason(f"manifest_series_rights_mismatch:{series_id}"))
    if instrument not in series.instrument_coverage:
        codes.append(_reason(f"manifest_series_instrument_uncovered:{series_id}"))
    return codes


# --- native book continuity -------------------------------------------------------------------------------------------


class _BookSide:
    """Exact price levels of one side: ascending price keys plus the canonical texts of each level."""

    def __init__(self) -> None:
        self.keys: list[Fraction] = []
        self.texts: dict[Fraction, tuple[str, str]] = {}

    def put(self, price: Fraction, price_text: str, quantity: Fraction, quantity_text: str) -> None:
        if quantity == 0:
            if price in self.texts:
                del self.texts[price]
                del self.keys[bisect_left(self.keys, price)]
            return
        if price not in self.texts:
            insort(self.keys, price)
        self.texts[price] = (price_text, quantity_text)


_ALIGNING = "aligning"
_APPLYING = "applying"
_INVALIDATED = "invalidated"


@dataclass
class _Segment:
    """Working state of the current snapshot-anchored segment; no segment means awaiting a snapshot."""

    anchor: ObservedBookSnapshot
    mode: str = _ALIGNING
    first: int | None = None
    last: int | None = None
    applied: int = 0
    emitted: int = 0
    stale: int = 0
    reobserved: int = 0
    depth: int = 0
    horizon: int = 0


@dataclass
class _BookOutcome:
    records: list[HistoricalPitRecord] = field(default_factory=list)
    segments: list[ObservedBookSegment] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    used_objects: set[str] = field(default_factory=set)
    disconnects: int = 0
    gaps: int = 0
    unanchored: int = 0
    invalidated: int = 0


class _BookReplay:
    """One pass over the capture in receipt order under the continuity profile; the first integrity defect stops it."""

    def __init__(self, stream: ObservedBookStream, instrument: str, declared: frozenset[str]) -> None:
        self.stream = stream
        self.instrument = instrument
        self.declared = declared
        self.outcome = _BookOutcome()
        self.segment: _Segment | None = None
        self.buffer: list[tuple[int, ObservedBookDelta]] = []
        self.bids = _BookSide()
        self.asks = _BookSide()
        self.horizon_bid = Fraction(0)
        self.horizon_ask = Fraction(0)
        self.last_applied = -1
        self.last_emitted = -1
        self.last_event_time = 0
        self.last_receipt = 0

    def fail(self, code: str) -> bool:
        self.outcome.codes.append(_reason(code))
        return False

    def run(self) -> _BookOutcome:
        for index, event in enumerate(self.stream.events):
            if not self.step(index, event):
                return self.outcome
        if self.segment is not None and self.segment.mode == _INVALIDATED:
            self.fail("book_sequence_gap_without_disconnect:end")
            return self.outcome
        self.close("end_of_input")
        self.outcome.unanchored += len(self.buffer)
        if not self.outcome.records:
            self.fail("book_no_eligible_observation")
        return self.outcome

    def step(self, index: int, event: ObservedBookEvent) -> bool:
        if event.object_id not in self.declared:
            return self.fail(f"source_object_undeclared:book:{index}")
        self.outcome.used_objects.add(event.object_id)
        if type(event) is ObservedDisconnect:
            self.disconnect()
            return True
        if event.receipt_ns < self.last_receipt:  # type: ignore[union-attr]
            return self.fail(f"book_receipt_time_regression:{index}")
        self.last_receipt = event.receipt_ns  # type: ignore[union-attr]
        if event.event_time_ns > event.receipt_ns:  # type: ignore[union-attr]
            return self.fail(f"book_event_after_receipt:{index}")
        if type(event) is ObservedBookSnapshot:
            return self.snapshot(index, event)
        return self.delta(index, event)  # type: ignore[arg-type]

    def disconnect(self) -> None:
        self.outcome.disconnects += 1
        if self.segment is not None:
            self.close("gap_then_disconnect" if self.segment.mode == _INVALIDATED else "disconnect")
        self.outcome.unanchored += len(self.buffer)
        self.buffer = []
        self.bids, self.asks = _BookSide(), _BookSide()

    def snapshot(self, index: int, snapshot: ObservedBookSnapshot) -> bool:
        if self.segment is not None:
            if self.segment.mode == _INVALIDATED:
                return self.fail(f"book_sequence_gap_without_disconnect:{index}")
            return self.fail(f"book_unjustified_resync:{index}")
        bids = _canonical_levels(snapshot.bids, "book_bids")
        asks = _canonical_levels(snapshot.asks, "book_asks")
        invalid = _snapshot_invalid(bids, asks)
        if invalid is not None:
            return self.fail(f"book_snapshot_invalid:{index}:{invalid}")
        if snapshot.last_update_id < self.last_applied:
            return self.fail(f"book_snapshot_regression:{index}")
        for side, levels in ((self.bids, bids), (self.asks, asks)):
            for price, price_text, quantity, quantity_text in levels:
                side.put(price, price_text, quantity, quantity_text)
        self.horizon_bid, self.horizon_ask = self.bids.keys[0], self.asks.keys[-1]
        segment = _Segment(anchor=snapshot)
        self.segment = segment
        buffered, self.buffer = self.buffer, []
        return all(self.anchored(position, delta, segment) for position, delta in buffered)

    def delta(self, index: int, delta: ObservedBookDelta) -> bool:
        if not (delta.previous_final_update_id < delta.first_update_id <= delta.final_update_id):
            return self.fail(f"book_delta_sequence_malformed:{index}")
        if self.segment is None:
            self.buffer.append((index, delta))
            return True
        return self.anchored(index, delta, self.segment)

    def anchored(self, index: int, delta: ObservedBookDelta, segment: _Segment) -> bool:
        if segment.mode == _INVALIDATED:
            self.outcome.invalidated += 1
            return True
        if segment.mode == _ALIGNING:
            if delta.final_update_id < segment.anchor.last_update_id:
                segment.stale += 1
                return True
            if not (delta.first_update_id <= segment.anchor.last_update_id <= delta.final_update_id):
                return self.fail(f"book_snapshot_alignment_failed:{index}")
        elif delta.final_update_id <= self.last_applied:
            return self.fail(f"book_sequence_regression:{index}")
        elif delta.previous_final_update_id != self.last_applied:
            segment.mode = _INVALIDATED
            self.outcome.gaps += 1
            self.outcome.invalidated += 1
            return True
        if delta.event_time_ns < self.last_event_time:
            return self.fail(f"book_event_time_regression:{index}")
        return self.apply(index, delta, segment)

    def apply(self, index: int, delta: ObservedBookDelta, segment: _Segment) -> bool:
        for side, levels, name in ((self.bids, delta.bids, "book_bids"), (self.asks, delta.asks, "book_asks")):
            canonical = _canonical_levels(levels, name)
            if len({price for price, _, _, _ in canonical}) != len(canonical):
                return self.fail(f"book_delta_price_duplicate:{index}")
            if any(price <= 0 or quantity < 0 for price, _, quantity, _ in canonical):
                return self.fail(f"book_delta_level_invalid:{index}")
            for price, price_text, quantity, quantity_text in canonical:
                side.put(price, price_text, quantity, quantity_text)
        if not self.bids.keys or not self.asks.keys:
            return self.fail(f"book_side_empty:{index}")
        if self.bids.keys[-1] >= self.asks.keys[0]:
            return self.fail(f"book_crossed:{index}")
        segment.mode = _APPLYING
        self.last_applied, self.last_event_time = delta.final_update_id, delta.event_time_ns
        segment.applied += 1
        segment.first = delta.final_update_id if segment.first is None else segment.first
        segment.last = delta.final_update_id
        depth = OBSERVED_PIT_BOOK_DEPTH
        if len(self.bids.keys) < depth or len(self.asks.keys) < depth:
            segment.depth += 1
        elif self.bids.keys[-depth] < self.horizon_bid or self.asks.keys[depth - 1] > self.horizon_ask:
            segment.horizon += 1
        elif delta.final_update_id <= self.last_emitted:
            segment.reobserved += 1
        else:
            self.emit(delta, segment)
        return True

    def emit(self, delta: ObservedBookDelta, segment: _Segment) -> None:
        available = max(delta.receipt_ns, segment.anchor.receipt_ns)
        self.outcome.records.append(
            build_historical_pit_record(
                series_id=self.stream.series_id,
                data_requirement_key=_ORDER_BOOK_KEY,
                instrument=self.instrument,
                sequence_id=delta.final_update_id,
                event_time_ns=delta.event_time_ns,
                available_at_ns=available,
                finalized_at_ns=available,
                revision_vintage_id=None,
                values=self.book_values(),
            )
        )
        self.last_emitted = delta.final_update_id
        segment.emitted += 1

    def book_values(self) -> tuple[HistoricalPitValue, ...]:
        depth = OBSERVED_PIT_BOOK_DEPTH
        bids = [self.bids.texts[price] for price in reversed(self.bids.keys[-depth:])]
        asks = [self.asks.texts[price] for price in self.asks.keys[:depth]]
        values = [
            HistoricalPitValue(BEST_BID_PRICE_NAME, bids[0][0]),
            HistoricalPitValue(BEST_BID_QUANTITY_NAME, bids[0][1]),
            HistoricalPitValue(BEST_ASK_PRICE_NAME, asks[0][0]),
            HistoricalPitValue(BEST_ASK_QUANTITY_NAME, asks[0][1]),
        ]
        for level, (bid, ask) in enumerate(zip(bids, asks, strict=True), 1):
            values.extend(
                (
                    HistoricalPitValue(f"bid_price_{level:02d}", bid[0]),
                    HistoricalPitValue(f"bid_quantity_{level:02d}", bid[1]),
                    HistoricalPitValue(f"ask_price_{level:02d}", ask[0]),
                    HistoricalPitValue(f"ask_quantity_{level:02d}", ask[1]),
                )
            )
        return tuple(values)

    def close(self, end_reason: str) -> None:
        segment = self.segment
        if segment is None:
            return
        self.outcome.segments.append(
            ObservedBookSegment(
                anchor_last_update_id=segment.anchor.last_update_id,
                anchor_receipt_ns=segment.anchor.receipt_ns,
                first_applied_final_update_id=segment.first,
                last_applied_final_update_id=segment.last,
                applied_delta_count=segment.applied,
                emitted_record_count=segment.emitted,
                stale_delta_count=segment.stale,
                reobserved_state_count=segment.reobserved,
                depth_ineligible_count=segment.depth,
                horizon_ineligible_count=segment.horizon,
                end_reason=end_reason,
            )
        )
        self.segment = None


def _snapshot_invalid(
    bids: tuple[tuple[Fraction, str, Fraction, str], ...], asks: tuple[tuple[Fraction, str, Fraction, str], ...]
) -> str | None:
    if not bids or not asks:
        return "side_empty"
    for side in (bids, asks):
        if any(price <= 0 or quantity <= 0 for price, _, quantity, _ in side):
            return "level_nonpositive"
        if len({price for price, _, _, _ in side}) != len(side):
            return "price_duplicate"
    if max(price for price, _, _, _ in bids) >= min(price for price, _, _, _ in asks):
        return "crossed"
    return None


# --- mark and funding -------------------------------------------------------------------------------------------------


def _mark_records(
    stream: ObservedMarkStream, instrument: str, declared: frozenset[str]
) -> tuple[list[HistoricalPitRecord], list[str], set[str]]:
    records: list[HistoricalPitRecord] = []
    used: set[str] = set()
    last_receipt = 0
    last_event = 0
    for index, item in enumerate(stream.observations):
        if item.object_id not in declared:
            return records, [_reason(f"source_object_undeclared:mark:{index}")], used
        used.add(item.object_id)
        if item.receipt_ns < last_receipt:
            return records, [_reason(f"mark_receipt_time_regression:{index}")], used
        if item.event_time_ns > item.receipt_ns:
            return records, [_reason(f"mark_event_after_receipt:{index}")], used
        if item.event_time_ns <= last_event:
            return records, [_reason(f"mark_event_time_not_increasing:{index}")], used
        if Fraction(item.mark_price) <= 0:
            return records, [_reason(f"mark_price_nonpositive:{index}")], used
        last_receipt, last_event = item.receipt_ns, item.event_time_ns
        records.append(
            build_historical_pit_record(
                series_id=stream.series_id,
                data_requirement_key=_MARK_KEY,
                instrument=instrument,
                sequence_id=item.event_time_ns,
                event_time_ns=item.event_time_ns,
                available_at_ns=item.receipt_ns,
                finalized_at_ns=item.receipt_ns,
                revision_vintage_id=None,
                values=(HistoricalPitValue(MARK_VALUE_NAME, item.mark_price),),
            )
        )
    return records, [], used


def _funding_records(
    stream: ObservedFundingStream, instrument: str, declared: frozenset[str]
) -> tuple[list[HistoricalPitRecord], list[str], set[str]]:
    interval, start, end = stream.governed_interval_ns, stream.coverage_start_ns, stream.coverage_end_ns
    used: set[str] = set()
    if start - interval <= 0:
        return [], [_reason("funding_window_open_invalid")], used
    by_index: dict[int, ObservedFundingSettlement] = {}
    identities: set[str] = set()
    last_time = 0
    for index, item in enumerate(stream.settlements):
        if item.object_id not in declared or item.published_object_id not in declared:
            return [], [_reason(f"source_object_undeclared:funding:{index}")], used
        used.update((item.object_id, item.published_object_id))
        if item.settlement_time_ns <= last_time or item.settlement_id in identities:
            return [], [_reason(f"funding_settlement_conflict:{index}")], used
        if not start <= item.settlement_time_ns < end:
            return [], [_reason(f"funding_settlement_outside_coverage:{index}")], used
        offset = item.settlement_time_ns - start
        if offset % interval:
            return [], [_reason(f"funding_settlement_off_grid:{index}")], used
        if item.published_observed_at_ns < item.settlement_time_ns:
            return [], [_reason(f"funding_final_observed_before_settlement:{index}")], used
        last_time = item.settlement_time_ns
        identities.add(item.settlement_id)
        by_index[offset // interval] = item
    expected = (end - start + interval - 1) // interval
    for position, grid_index in enumerate(sorted(by_index)):
        if grid_index != position:
            return [], [_reason(f"funding_coverage_incomplete:{position}")], used
    if len(by_index) != expected:
        return [], [_reason(f"funding_coverage_incomplete:{len(by_index)}")], used
    records = [
        build_historical_pit_record(
            series_id=stream.series_id,
            data_requirement_key=_FUNDING_KEY,
            instrument=instrument,
            sequence_id=grid_index,
            event_time_ns=item.settlement_time_ns - interval,
            available_at_ns=item.published_observed_at_ns,
            finalized_at_ns=item.settlement_time_ns,
            revision_vintage_id=None,
            values=(HistoricalPitValue(FUNDING_VALUE_NAME, item.funding_rate),),
        )
        for grid_index, item in sorted(by_index.items())
    ]
    return records, [], used


# --- assembly ---------------------------------------------------------------------------------------------------------


def _assemble(inputs: object) -> ObservedPitIngressResult:
    """The one ingress assembly path, shared by the builder and the verifier reassembly."""

    if type(inputs) is not ObservedPitIngressInputs:
        raise _fail("inputs_malformed")
    ingress_id = _require_text(inputs.ingress_id, "ingress_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    dataset_id = _require_text(inputs.dataset_id, "dataset_id")
    instrument = _require_instrument(inputs.instrument)
    declaration = _canonical_declaration(inputs.declaration)
    book = _canonical_book_stream(inputs.book)
    mark = _canonical_mark_stream(inputs.mark)
    funding = _canonical_funding_stream(inputs.funding)
    if len({book.series_id, mark.series_id, funding.series_id}) != 3:
        raise _fail("series_ids_not_distinct")
    for anchor, name in (
        (inputs.expected_source_manifest_digest, "expected_source_manifest_digest"),
        (inputs.expected_data_requirement_registry_digest, "expected_data_requirement_registry_digest"),
    ):
        if not edge_is_hex64(anchor):
            raise _fail(f"{name}_invalid")
    if type(inputs.source_manifest) is not EdgeSourcePacketEvidence:
        raise _fail("source_manifest_malformed")
    try:
        manifest_payload = edge_source_packet_evidence_to_dict(inputs.source_manifest)
    except Exception as exc:  # noqa: BLE001 - a hollow manifest object is a construction error, never a receipt
        raise _fail("source_manifest_not_serializable") from exc
    binding = build_edge_authority_binding(
        snapshot_payload=manifest_payload,
        expected_digest=inputs.expected_source_manifest_digest,
        shape=edge_source_packet_evidence_payload_is_well_formed,
        error=ObservedPitIngressError,
        code=_reason("source_manifest"),
    )
    manifest = edge_source_packet_evidence_from_payload(edge_authority_binding_snapshot(binding))
    registry_digest = inputs.expected_data_requirement_registry_digest
    codes = _manifest_codes(
        manifest, anchor=binding.expected_digest, correlation_id=correlation_id, registry_digest=registry_digest
    )
    if not codes:
        for stream_series, reference, key in (
            (book.series_id, book.source_reference, _ORDER_BOOK_KEY),
            (mark.series_id, mark.source_reference, _MARK_KEY),
            (funding.series_id, funding.source_reference, _FUNDING_KEY),
        ):
            codes.extend(
                _series_codes(
                    manifest,
                    series_id=stream_series,
                    source_reference=reference,
                    key=key,
                    instrument=instrument,
                    declaration=declaration,
                )
            )

    declared = frozenset(item.object_id for item in declaration.objects)
    book_outcome = _BookReplay(book, instrument, declared).run()
    mark_records, mark_codes, mark_used = _mark_records(mark, instrument, declared)
    funding_records, funding_codes, funding_used = _funding_records(funding, instrument, declared)
    codes.extend(book_outcome.codes + mark_codes + funding_codes)
    if not (book_outcome.codes or mark_codes or funding_codes):
        used = book_outcome.used_objects | mark_used | funding_used
        codes.extend(_reason(f"source_object_unused:{object_id}") for object_id in sorted(declared - used))

    declaration_digest = edge_sha256_text(edge_canonical_json(_to_payload(declaration)))
    observation_digest = _observation_digest(book, mark, funding)
    dataset: HistoricalPitDataset | None = None
    if not codes:
        dataset = build_historical_pit_dataset(
            inputs.source_manifest,
            expected_source_manifest_digest=binding.expected_digest,
            expected_data_requirement_registry_digest=registry_digest,
            dataset_id=dataset_id,
            correlation_id=correlation_id,
            source_reference=f"{_DATASET_SOURCE_REFERENCE_PREFIX}{declaration_digest}",
            rights_status=declaration.rights_status,
            rights_reference=declaration.rights_reference,
            records=tuple(book_outcome.records + mark_records + funding_records),
        )
        if dataset.status is not EdgeEvidenceStatus.READY:
            codes.extend(_reason(f"dataset_rejected:{code}") for code in dataset.integrity_reason_codes)
    integrity = _sorted_unique(codes)

    ready_dataset = dataset if dataset is not None and not integrity else None
    if ready_dataset is None:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        fail: list[str] = []
        needs_external: list[str] = []
        needs_governance: list[str] = []
        if not _CONTINUITY_PROFILE_QUALIFIED:
            needs_external.append(_reason(f"continuity_profile_not_qualified:{OBSERVED_PIT_CONTINUITY_PROFILE_ID}"))
        upstream = list(ready_dataset.verdict_reason_codes)
        if ready_dataset.gate_verdict is EdgeGateVerdict.FAIL:
            fail.extend(upstream)
        elif ready_dataset.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
            needs_external.extend(upstream)
        elif ready_dataset.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
            needs_governance.extend(upstream)
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    seed = ObservedPitIngressEvidence(
        schema_version=_SCHEMA_VERSION,
        contract_id=OBSERVED_PIT_INGRESS_CONTRACT_ID,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        ingress_id=ingress_id,
        correlation_id=correlation_id,
        dataset_id=dataset_id,
        instrument=instrument,
        source_id=declaration.source_id,
        source_contract_reference=declaration.source_contract_reference,
        rights_status=declaration.rights_status.value,
        rights_reference=declaration.rights_reference,
        source_objects=declaration.objects,
        declaration_digest=declaration_digest,
        observation_digest=observation_digest,
        source_manifest_digest=binding.expected_digest,
        data_requirement_registry_digest=registry_digest,
        continuity_profile_id=OBSERVED_PIT_CONTINUITY_PROFILE_ID,
        continuity_profile_digest=observed_pit_continuity_profile_digest(),
        book_series_id=book.series_id,
        mark_series_id=mark.series_id,
        funding_series_id=funding.series_id,
        book_sequence_identity=_BOOK_SEQUENCE_IDENTITY,
        mark_sequence_identity=_MARK_SEQUENCE_IDENTITY,
        funding_sequence_identity=_FUNDING_SEQUENCE_IDENTITY,
        book_segments=tuple(book_outcome.segments),
        book_disconnect_count=book_outcome.disconnects,
        book_gap_count=book_outcome.gaps,
        book_unanchored_delta_count=book_outcome.unanchored,
        book_invalidated_delta_count=book_outcome.invalidated,
        book_record_count=len(book_outcome.records),
        mark_record_count=len(mark_records),
        funding_record_count=len(funding_records),
        funding_interval_ns=funding.governed_interval_ns,
        funding_interval_reference=funding.interval_reference,
        funding_coverage_start_ns=funding.coverage_start_ns,
        funding_coverage_end_ns=funding.coverage_end_ns,
        dataset_digest="" if dataset is None else dataset.dataset_digest,
        dataset_status="" if dataset is None else dataset.status.value,
        dataset_gate_verdict="" if dataset is None else dataset.gate_verdict.value,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        ingress_digest="",
    )
    return ObservedPitIngressResult(evidence=replace(seed, ingress_digest=_digest(seed)), dataset=ready_dataset)


def _digest(evidence: ObservedPitIngressEvidence) -> str:
    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


def _observation_digest(book: ObservedBookStream, mark: ObservedMarkStream, funding: ObservedFundingStream) -> str:
    """Digest of the EXACT capture, every event kind-tagged, so an evidence identifies its inputs, not only outputs."""

    payload = {
        "book": {
            **{name: value for name, value in _to_payload(book).items() if name != "events"},
            "events": [{"kind": type(event).__name__, **_to_payload(event)} for event in book.events],
        },
        "mark": _to_payload(mark),
        "funding": _to_payload(funding),
    }
    return edge_sha256_text(edge_canonical_json(payload))


# --- public API -------------------------------------------------------------------------------------------------------


def observed_pit_continuity_profile() -> dict[str, str]:
    """A copy of the one code-defined continuity profile (documented, not qualified)."""

    return dict(_CONTINUITY_PROFILE)


def observed_pit_continuity_profile_digest() -> str:
    return edge_sha256_text(edge_canonical_json(_CONTINUITY_PROFILE))


def observed_pit_implemented_series_semantics() -> dict[str, dict[str, object]]:
    """A copy of exactly the registry-derived EF-3 series semantics this module implements, per data key."""

    return {key: dict(value) for key, value in _IMPLEMENTED_SERIES_SEMANTICS.items()}


def build_observed_pit_ingress(inputs: ObservedPitIngressInputs) -> ObservedPitIngressResult:
    """Validate captured observations and assemble the accepted PIT dataset over an authenticated EF-3 manifest.

    Malformed caller input raises ``ObservedPitIngressError``. An integrity defect in the observations, their
    provenance, the continuity of the native book, the upstream manifest or the assembled dataset yields ``REJECTED``
    evidence and no dataset. A READY evidence carries the dataset and never advances while the continuity profile is
    not qualified. Pure: no IO, clock, randomness, network or environment access.
    """

    return _assemble(inputs)


def observed_pit_ingress_to_dict(evidence: ObservedPitIngressEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of an ingress evidence, including its self-digest."""

    return _to_payload(evidence)


def observed_pit_ingress_digest(evidence: ObservedPitIngressEvidence) -> str:
    """Recompute the canonical ingress digest, excluding only ``ingress_digest``."""

    return _digest(evidence)


def verify_observed_pit_ingress(evidence: object, inputs: object) -> EdgeEvidenceVerification:
    """Re-prove an evidence by rebuilding it from its exact inputs and comparing typed identity. Total: never raises."""

    stage = "evidence_type_invalid"
    try:
        if type(evidence) is not ObservedPitIngressEvidence:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        canonical = edge_canonical_json(_to_payload(evidence))
        carried = json.loads(canonical)
        recomputed = edge_payload_digest(carried, _SELF_DIGEST_FIELD)
        stage = "evidence_reassembly_failed"
        rebuilt = _assemble(inputs).evidence
        expected = json.loads(edge_canonical_json(_to_payload(rebuilt)))
        codes: set[str] = set()
        if carried[_SELF_DIGEST_FIELD] != recomputed:
            codes.add(_reason("self_digest_mismatch"))
        for name in set(expected) | set(carried):
            if name not in expected or name not in carried:
                codes.add(_reason(f"field_mismatch:{name}"))
            elif edge_canonical_json(expected[name]) != edge_canonical_json(carried[name]):
                codes.add(_reason(f"field_mismatch:{name}"))
        if not _typed_identical(evidence, rebuilt):
            codes.add(_reason("typed_identity_mismatch"))
        reason_codes = tuple(sorted(codes))
        return EdgeEvidenceVerification(
            intact=not reason_codes, reason_codes=reason_codes, recomputed_digest=recomputed, canonical_json=canonical
        )
    except Exception:  # noqa: BLE001 - VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT
        return EdgeEvidenceVerification(False, (_reason(stage),), "", "")


__all__ = [
    "OBSERVED_PIT_BOOK_DEPTH",
    "OBSERVED_PIT_CONTINUITY_PROFILE_ID",
    "OBSERVED_PIT_INGRESS_CONTRACT_ID",
    "OBSERVED_PIT_INGRESS_NON_CLAIM_FLAGS",
    "ObservedBookDelta",
    "ObservedBookEvent",
    "ObservedBookLevel",
    "ObservedBookSegment",
    "ObservedBookSnapshot",
    "ObservedBookStream",
    "ObservedDisconnect",
    "ObservedFundingSettlement",
    "ObservedFundingStream",
    "ObservedMarkObservation",
    "ObservedMarkStream",
    "ObservedPitIngressError",
    "ObservedPitIngressEvidence",
    "ObservedPitIngressInputs",
    "ObservedPitIngressResult",
    "ObservedSourceDeclaration",
    "ObservedSourceObject",
    "build_observed_pit_ingress",
    "observed_pit_continuity_profile",
    "observed_pit_continuity_profile_digest",
    "observed_pit_implemented_series_semantics",
    "observed_pit_ingress_digest",
    "observed_pit_ingress_to_dict",
    "verify_observed_pit_ingress",
]
