"""Deterministic historical point-in-time (PIT) dataset authority.

A ``HistoricalPitDataset`` binds an ordered set of immutable historical observations to the authenticated series
semantics of an accepted EF-3 ``EdgeSourcePacketEvidence`` manifest and its ``DataRequirementRegistry`` digest.

What it proves:

* deterministic content identity — every record carries a self-digest recomputed on every assembly, records are held
  in one canonical order, and the dataset self-digest covers them all;
* internal PIT consistency — no record is available or finalized before its event time, logical record identity
  ``(series_id, instrument, sequence_id)`` is unique unless the authenticated series is revised with point-in-time
  vintages, and sequence order never runs backwards in event time; a funding series (authenticated
  ``funding_semantics`` present) carries exactly one settlement per event time and contiguous sequence ids;
* binding to authenticated declared data semantics — every record's series, data requirement key and instrument must
  match the authenticated EF-3 series record; finality and revision behavior are derived from EF-3 (``finalized_only``,
  ``funding_semantics``, ``revision_policy``), never from caller labels.

What it does NOT prove: that the source archive is historically complete or honest. ``external_archive_truth_proven``
is structurally False.

PIT view: at decision time ``t`` a record is visible only when ``available_at_ns <= t``; for a series whose
authenticated semantics require final data it must also carry ``finalized_at_ns <= t``. A non-final observation never
becomes final. For vintage-revised series only the latest vintage available at ``t`` is visible per logical record.

Numeric values use one ASCII canonical decimal grammar (18 fraction digits, no exponent, no plus sign, no negative
zero, no Unicode digits) with a representation-safety bound of 60 characters; native integer wire fields (sequence ids
and nanosecond timestamps) are bounded to signed int64 by integer comparison before any serialization. Both bounds are
representation safety only, never trading or data-quality thresholds, and never depend on interpreter digit-limit
settings. The strict parser refuses values outside them, so builder, parser and verifier share one domain. Status is
integrity only (READY/REJECTED); the verdict is the outcome; REJECTED implies
NOT_EVALUATED and only READY + PASS advances. One assembly path serves the builder and verifier reassembly;
``verify_historical_pit_dataset`` is total. Deterministic, historical-evaluation only: no IO, clock, randomness,
network, environment, orders, fills, PnL or metrics.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum

from crypto_core.data.requirements import DataRequirementKey
from crypto_core.strategy.source_packet import SourcePacketRightsStatus
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeArtifactError,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    build_edge_authority_binding,
    edge_authority_binding_snapshot,
    edge_authority_binding_to_payload,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    parse_edge_authority_binding,
    require_edge_authority_binding,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourcePacketEvidence,
    edge_source_packet_evidence_from_payload,
    edge_source_packet_evidence_payload_is_well_formed,
    edge_source_packet_evidence_to_dict,
    verify_edge_source_packet_evidence,
)

_SCHEMA_VERSION = "historical-pit-dataset.v1"
_REASON_PREFIX = "historical_pit_dataset"
_SELF_DIGEST_FIELD = "dataset_digest"
_RECORD_DIGEST_FIELD = "record_digest"
_CANONICAL_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]{18}")
_NEGATIVE_ZERO = "-0.000000000000000000"
_MAX_SCALE18_TEXT_LENGTH = 60
_MAX_WIRE_INT = 9223372036854775807
_VINTAGE_REVISION = "revised_with_point_in_time_vintages"
_INSTRUMENT_EXTRA_CHARS = frozenset("-_./:")
_DATA_REQUIREMENT_KEY_VALUES = frozenset(key.value for key in DataRequirementKey)

HISTORICAL_PIT_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    ("pbo_passed", False),
    ("stress_passed", False),
    ("external_archive_truth_proven", False),
    ("orders_created", False),
    ("fills_simulated", False),
    ("pnl_computed", False),
    ("performance_metrics_computed", False),
)
_FLAG_NAMES = frozenset(name for name, _ in HISTORICAL_PIT_NON_CLAIM_FLAGS)


class HistoricalPitDatasetError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


@dataclass(frozen=True)
class HistoricalPitValue:
    """One named canonical decimal value of an observation."""

    name: str
    value: str


@dataclass(frozen=True)
class HistoricalPitRecord:
    """One immutable historical observation; ``record_digest`` covers every other field."""

    series_id: str
    data_requirement_key: str
    instrument: str
    sequence_id: int
    event_time_ns: int
    available_at_ns: int
    finalized_at_ns: int | None
    revision_vintage_id: str | None
    values: tuple[HistoricalPitValue, ...]
    record_digest: str


@dataclass(frozen=True)
class HistoricalPitSeriesSemantics:
    """Series semantics derived only from the authenticated EF-3 series record."""

    series_id: str
    data_requirement_key: str
    instrument_coverage: tuple[str, ...]
    funding_semantics: str | None
    revision_policy: str
    final_required: bool
    feature_input_eligible: bool


@dataclass(frozen=True)
class HistoricalPitDataset:
    """Immutable, digest-bound historical PIT dataset authority. Historical evaluation only; proves no edge."""

    schema_version: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    dataset_id: str
    correlation_id: str
    source_reference: str
    rights_status: str
    rights_reference: str
    source_manifest_binding: EdgeAuthorityBinding
    source_manifest_digest: str
    expected_data_requirement_registry_digest: str
    data_requirement_registry_digest: str
    series_semantics: tuple[HistoricalPitSeriesSemantics, ...]
    records: tuple[HistoricalPitRecord, ...]
    record_digests: tuple[str, ...]
    series_ids: tuple[str, ...]
    instruments: tuple[str, ...]
    coverage_first_event_time_ns: int
    coverage_last_event_time_ns: int
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    dataset_digest: str
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
    pbo_passed: bool = False
    stress_passed: bool = False
    external_archive_truth_proven: bool = False
    orders_created: bool = False
    fills_simulated: bool = False
    pnl_computed: bool = False
    performance_metrics_computed: bool = False


@dataclass(frozen=True)
class HistoricalPitView:
    """Records of one series and instrument visible at ``decision_time_ns`` under the authenticated semantics."""

    dataset_digest: str
    series_id: str
    instrument: str
    decision_time_ns: int
    final_required: bool
    records: tuple[HistoricalPitRecord, ...]


# --- strict helpers ---------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> HistoricalPitDatasetError:
    return HistoricalPitDatasetError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def is_canonical_pit_decimal(value: object) -> bool:
    """ASCII canonical decimal: optional minus, no leading zeros, exactly 18 fraction digits, no negative zero, <= 60."""

    return (
        type(value) is str
        and len(value) <= _MAX_SCALE18_TEXT_LENGTH
        and _CANONICAL_DECIMAL.fullmatch(value) is not None
        and value != _NEGATIVE_ZERO
    )


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
        raise _fail("record_instrument_invalid")
    if any(not (char.isascii() and (char.isalnum() or char in _INSTRUMENT_EXTRA_CHARS)) for char in value):
        raise _fail("record_instrument_invalid")
    return _require_text(value, "record_instrument")


def _require_positive_int(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0 or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    return value


def _require_nonnegative_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    return value


def _serialize(value: object) -> object:
    if type(value) is EdgeAuthorityBinding:
        return edge_authority_binding_to_payload(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


# --- records ----------------------------------------------------------------------------------------------------------


def _canonical_values(values: object) -> tuple[HistoricalPitValue, ...]:
    if type(values) not in (tuple, list):
        raise _fail("record_values_malformed")
    canonical: dict[str, HistoricalPitValue] = {}
    for item in values:  # type: ignore[union-attr]
        if type(item) is not HistoricalPitValue:
            raise _fail("record_value_malformed")
        name = _require_token(item.name, "record_value_name")
        if not is_canonical_pit_decimal(item.value):
            raise _fail("record_value_noncanonical")
        if name in canonical:
            raise _fail("record_value_name_duplicate")
        canonical[name] = HistoricalPitValue(name=name, value=item.value)
    if not canonical:
        raise _fail("record_values_empty")
    return tuple(canonical[key] for key in sorted(canonical))


def _canonical_record_body(record: object) -> HistoricalPitRecord:
    """Validate every caller field of a record and return it with an empty digest slot."""

    if type(record) is not HistoricalPitRecord:
        raise _fail("record_malformed")
    key = _require_token(record.data_requirement_key, "record_data_requirement_key")
    if key not in _DATA_REQUIREMENT_KEY_VALUES:
        raise _fail("record_data_requirement_key_unknown")
    finalized_at_ns = record.finalized_at_ns
    vintage = record.revision_vintage_id
    return HistoricalPitRecord(
        series_id=_require_token(record.series_id, "record_series_id"),
        data_requirement_key=key,
        instrument=_require_instrument(record.instrument),
        sequence_id=_require_nonnegative_int(record.sequence_id, "record_sequence_id"),
        event_time_ns=_require_positive_int(record.event_time_ns, "record_event_time_ns"),
        available_at_ns=_require_positive_int(record.available_at_ns, "record_available_at_ns"),
        finalized_at_ns=None
        if finalized_at_ns is None
        else _require_positive_int(finalized_at_ns, "record_finalized_at_ns"),
        revision_vintage_id=None if vintage is None else _require_token(vintage, "record_revision_vintage_id"),
        values=_canonical_values(record.values),
        record_digest="",
    )


def build_historical_pit_record(
    *,
    series_id: str,
    data_requirement_key: str,
    instrument: str,
    sequence_id: int,
    event_time_ns: int,
    available_at_ns: int,
    finalized_at_ns: int | None,
    revision_vintage_id: str | None,
    values: Sequence[HistoricalPitValue],
) -> HistoricalPitRecord:
    """Build one canonical record whose ``record_digest`` is computed here, never supplied."""

    body = _canonical_record_body(
        HistoricalPitRecord(
            series_id=series_id,
            data_requirement_key=data_requirement_key,
            instrument=instrument,
            sequence_id=sequence_id,
            event_time_ns=event_time_ns,
            available_at_ns=available_at_ns,
            finalized_at_ns=finalized_at_ns,
            revision_vintage_id=revision_vintage_id,
            values=values,  # type: ignore[arg-type]
            record_digest="",
        )
    )
    return replace(body, record_digest=historical_pit_record_digest(body))


def historical_pit_record_digest(record: HistoricalPitRecord) -> str:
    """Recompute a record's canonical digest, excluding only ``record_digest``."""

    return edge_payload_digest(_to_payload(record), _RECORD_DIGEST_FIELD)


def _record_sort_key(record: HistoricalPitRecord) -> tuple[object, ...]:
    return (
        record.series_id,
        record.instrument,
        record.sequence_id,
        record.available_at_ns,
        record.revision_vintage_id or "",
        record.record_digest,
    )


# --- authority ---------------------------------------------------------------------------------------------------------


def _source_manifest_authority(
    binding: EdgeAuthorityBinding, *, correlation_id: str
) -> tuple[list[str], EdgeSourcePacketEvidence | None]:
    manifest = edge_source_packet_evidence_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_source_packet_evidence(manifest)
    if not verification.intact:
        return [_reason(f"source_manifest_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("source_manifest_digest_mismatch")], None
    if manifest.correlation_id != correlation_id:
        return [_reason("source_manifest_correlation_mismatch")], None
    if manifest.status is not EdgeEvidenceStatus.READY:
        return [_reason("source_manifest_rejected")], None
    return [], manifest


def _series_semantics(manifest: EdgeSourcePacketEvidence) -> tuple[HistoricalPitSeriesSemantics, ...]:
    return tuple(
        HistoricalPitSeriesSemantics(
            series_id=record.series_id,
            data_requirement_key=record.data_requirement_key,
            instrument_coverage=record.instrument_coverage,
            funding_semantics=record.funding_semantics,
            revision_policy=record.revision_policy,
            final_required=record.finalized_only is True,
            feature_input_eligible=record.feature_input_eligible is True,
        )
        for record in manifest.series
    )


def _record_integrity_codes(
    records: Sequence[HistoricalPitRecord], semantics: Sequence[HistoricalPitSeriesSemantics] | None
) -> list[str]:
    codes: list[str] = []
    by_series = {} if semantics is None else {item.series_id: item for item in semantics}
    identities: dict[tuple[str, str, int], list[HistoricalPitRecord]] = {}
    for record in records:
        if record.record_digest != historical_pit_record_digest(replace(record, record_digest="")):
            codes.append(_reason(f"record_digest_mismatch:{record.series_id}:{record.instrument}:{record.sequence_id}"))
        ref = f"{record.series_id}:{record.instrument}:{record.sequence_id}"
        if record.available_at_ns < record.event_time_ns or (
            record.finalized_at_ns is not None and record.finalized_at_ns < record.event_time_ns
        ):
            codes.append(_reason(f"record_time_order_invalid:{ref}"))
        identities.setdefault((record.series_id, record.instrument, record.sequence_id), []).append(record)
        if semantics is None:
            continue
        series = by_series.get(record.series_id)
        if series is None:
            codes.append(_reason(f"record_series_unknown:{record.series_id}"))
            continue
        if record.data_requirement_key != series.data_requirement_key:
            codes.append(_reason(f"record_data_requirement_key_mismatch:{ref}"))
        if record.instrument not in series.instrument_coverage:
            codes.append(_reason(f"record_instrument_foreign:{ref}"))
        if record.revision_vintage_id is not None and series.revision_policy != _VINTAGE_REVISION:
            codes.append(_reason(f"record_revision_unsupported:{ref}"))
    for (series_id, instrument, sequence_id), group in identities.items():
        if len(group) == 1:
            continue
        ref = f"{series_id}:{instrument}:{sequence_id}"
        series = by_series.get(series_id)
        vintages = [record.revision_vintage_id for record in group]
        availability = [record.available_at_ns for record in group]
        valid_vintage_group = (
            series is not None
            and series.revision_policy == _VINTAGE_REVISION
            and None not in vintages
            and len(set(vintages)) == len(vintages)
            and len(set(availability)) == len(availability)
            and len({record.event_time_ns for record in group}) == 1
        )
        if not valid_vintage_group:
            codes.append(_reason(f"record_identity_duplicate:{ref}"))
    streams: dict[tuple[str, str], dict[int, int]] = {}
    for record in records:
        events = streams.setdefault((record.series_id, record.instrument), {})
        events[record.sequence_id] = min(events.get(record.sequence_id, record.event_time_ns), record.event_time_ns)
    for (series_id, instrument), events in streams.items():
        ordered = sorted(events.items())
        pairs = list(zip(ordered, ordered[1:], strict=False))
        if any(later[1] < earlier[1] for earlier, later in pairs):
            codes.append(_reason(f"sequence_non_monotonic:{series_id}:{instrument}"))
        series = by_series.get(series_id)
        if series is None or series.funding_semantics is None:
            continue
        if any(later[1] == earlier[1] for earlier, later in pairs):
            codes.append(_reason(f"record_logical_duplicate:{series_id}:{instrument}"))
        if any(later[0] != earlier[0] + 1 for earlier, later in pairs):
            codes.append(_reason(f"sequence_gap:{series_id}:{instrument}"))
    return codes


# --- dataset ----------------------------------------------------------------------------------------------------------


def _assemble_dataset(
    *,
    source_manifest_binding: object,
    dataset_id: object,
    correlation_id: object,
    source_reference: object,
    rights_status: object,
    rights_reference: object,
    expected_data_requirement_registry_digest: object,
    records: object,
) -> HistoricalPitDataset:
    """The one dataset assembly path, shared by the builder and verifier reassembly."""

    manifest_binding = require_edge_authority_binding(
        source_manifest_binding,
        shape=edge_source_packet_evidence_payload_is_well_formed,
        error=HistoricalPitDatasetError,
        code=_reason("source_manifest"),
        optional=False,
    )
    dataset_id = _require_text(dataset_id, "dataset_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    source_reference = _require_text(source_reference, "source_reference")
    rights_reference = _require_text(rights_reference, "rights_reference")
    if type(rights_status) is SourcePacketRightsStatus:
        rights = rights_status
    elif type(rights_status) is str and rights_status in {member.value for member in SourcePacketRightsStatus}:
        rights = SourcePacketRightsStatus(rights_status)
    else:
        raise _fail("rights_status_invalid")
    if not edge_is_hex64(expected_data_requirement_registry_digest):
        raise _fail("expected_data_requirement_registry_digest_invalid")
    if type(records) not in (tuple, list):
        raise _fail("records_malformed")
    canonical_records: list[HistoricalPitRecord] = []
    for record in records:  # type: ignore[union-attr]
        body = _canonical_record_body(record)
        carried = record.record_digest  # type: ignore[attr-defined]
        if not edge_is_hex64(carried):
            raise _fail("record_digest_invalid")
        canonical_records.append(replace(body, record_digest=carried))
    if not canonical_records:
        raise _fail("records_empty")
    ordered = tuple(sorted(canonical_records, key=_record_sort_key))

    manifest_codes, manifest = _source_manifest_authority(manifest_binding, correlation_id=correlation_id)  # type: ignore[arg-type]
    semantics = None if manifest is None else _series_semantics(manifest)
    codes = list(manifest_codes)
    if manifest is not None and manifest.data_requirement_registry_digest != expected_data_requirement_registry_digest:
        codes.append(_reason("data_requirement_registry_mismatch"))
    codes.extend(_record_integrity_codes(ordered, semantics))
    integrity = _sorted_unique(codes)

    if integrity or manifest is None:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        fail: list[str] = []
        needs_external: list[str] = []
        needs_governance: list[str] = []
        if manifest.advances is not True:
            code = _reason(f"source_manifest_not_advanced:{manifest.gate_verdict.value}")
            if manifest.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
                needs_external.append(code)
            elif manifest.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
                needs_governance.append(code)
            else:
                fail.append(code)
        if rights is SourcePacketRightsStatus.RESTRICTED:
            fail.append(_reason("dataset_rights_restricted"))
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    seed = HistoricalPitDataset(
        schema_version=_SCHEMA_VERSION,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        dataset_id=dataset_id,
        correlation_id=correlation_id,
        source_reference=source_reference,
        rights_status=rights.value,
        rights_reference=rights_reference,
        source_manifest_binding=manifest_binding,  # type: ignore[arg-type]
        source_manifest_digest=manifest_binding.expected_digest,  # type: ignore[union-attr]
        expected_data_requirement_registry_digest=expected_data_requirement_registry_digest,  # type: ignore[arg-type]
        data_requirement_registry_digest="" if manifest is None else manifest.data_requirement_registry_digest,
        series_semantics=() if semantics is None else semantics,
        records=ordered,
        record_digests=tuple(record.record_digest for record in ordered),
        series_ids=tuple(sorted({record.series_id for record in ordered})),
        instruments=tuple(sorted({record.instrument for record in ordered})),
        coverage_first_event_time_ns=min(record.event_time_ns for record in ordered),
        coverage_last_event_time_ns=max(record.event_time_ns for record in ordered),
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        dataset_digest="",
    )
    return replace(seed, dataset_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_historical_pit_dataset(
    source_manifest: EdgeSourcePacketEvidence,
    *,
    expected_source_manifest_digest: str,
    expected_data_requirement_registry_digest: str,
    dataset_id: str,
    correlation_id: str,
    source_reference: str,
    rights_status: SourcePacketRightsStatus | str,
    rights_reference: str,
    records: Sequence[HistoricalPitRecord],
) -> HistoricalPitDataset:
    """Build a deterministic historical PIT dataset over an authenticated EF-3 source manifest.

    Malformed caller input or a non-serializable upstream object raises ``HistoricalPitDatasetError``. An EF-3
    manifest or registry that fails re-proof, or any record-integrity violation, yields ``REJECTED``/``NOT_EVALUATED``.
    Otherwise the dataset is ``READY`` with ``PASS``, or propagates the manifest's blocking verdict (restricted rights
    are ``FAIL``).
    """

    if type(source_manifest) is not EdgeSourcePacketEvidence:
        raise _fail("source_manifest_malformed")
    try:
        manifest_payload = edge_source_packet_evidence_to_dict(source_manifest)
    except Exception as exc:  # noqa: BLE001 - a hollow manifest object is a construction error, never a receipt
        raise _fail("source_manifest_not_serializable") from exc
    manifest_binding = build_edge_authority_binding(
        snapshot_payload=manifest_payload,
        expected_digest=expected_source_manifest_digest,
        shape=edge_source_packet_evidence_payload_is_well_formed,
        error=HistoricalPitDatasetError,
        code=_reason("source_manifest"),
    )
    return _assemble_dataset(
        source_manifest_binding=manifest_binding,
        dataset_id=dataset_id,
        correlation_id=correlation_id,
        source_reference=source_reference,
        rights_status=rights_status,
        rights_reference=rights_reference,
        expected_data_requirement_registry_digest=expected_data_requirement_registry_digest,
        records=records,
    )


def historical_pit_dataset_to_dict(dataset: HistoricalPitDataset) -> dict[str, object]:
    """Canonical JSON-ready mapping for a dataset, including its self-digest."""

    return _to_payload(dataset)


def historical_pit_dataset_digest(dataset: HistoricalPitDataset) -> str:
    """Recompute the canonical dataset digest, excluding only ``dataset_digest``."""

    return edge_payload_digest(_to_payload(dataset), _SELF_DIGEST_FIELD)


# --- strict parsing ------------------------------------------------------------------------------------------------------


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


def _as_canonical_decimal(value: object) -> str:
    if not is_canonical_pit_decimal(value):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


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


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


def _parse_manifest_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_source_packet_evidence_payload_is_well_formed,
        error=HistoricalPitDatasetError,
        code=_reason("source_manifest"),
        optional=False,
    )


_RECORD_CONVERTERS: dict[str, Callable[[object], object]] = {
    "sequence_id": _as_int,
    "event_time_ns": _as_int,
    "available_at_ns": _as_int,
    "finalized_at_ns": _as_optional_int,
    "revision_vintage_id": _as_optional_str,
    "values": _as_records(HistoricalPitValue, {"value": _as_canonical_decimal}),
}
_DATASET_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "source_manifest_binding": _parse_manifest_binding,
    "series_semantics": _as_records(
        HistoricalPitSeriesSemantics,
        {
            "instrument_coverage": _as_str_tuple,
            "funding_semantics": _as_optional_str,
            "final_required": _as_bool,
            "feature_input_eligible": _as_bool,
        },
    ),
    "records": _as_records(HistoricalPitRecord, _RECORD_CONVERTERS),
    "record_digests": _as_str_tuple,
    "series_ids": _as_str_tuple,
    "instruments": _as_str_tuple,
    "coverage_first_event_time_ns": _as_int,
    "coverage_last_event_time_ns": _as_int,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def historical_pit_dataset_from_payload(payload: object) -> HistoricalPitDataset:
    """Strictly reconstruct a dataset from its serialized payload (exact fields and types; no semantic proof)."""

    return _parse_exact(HistoricalPitDataset, payload, _DATASET_CONVERTERS)  # type: ignore[return-value]


def historical_pit_dataset_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a dataset snapshot."""

    try:
        historical_pit_dataset_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_dataset(dataset: object) -> HistoricalPitDataset:
    return _assemble_dataset(
        source_manifest_binding=dataset.source_manifest_binding,  # type: ignore[attr-defined]
        dataset_id=dataset.dataset_id,  # type: ignore[attr-defined]
        correlation_id=dataset.correlation_id,  # type: ignore[attr-defined]
        source_reference=dataset.source_reference,  # type: ignore[attr-defined]
        rights_status=dataset.rights_status,  # type: ignore[attr-defined]
        rights_reference=dataset.rights_reference,  # type: ignore[attr-defined]
        expected_data_requirement_registry_digest=dataset.expected_data_requirement_registry_digest,  # type: ignore[attr-defined]
        records=dataset.records,  # type: ignore[attr-defined]
    )


def verify_historical_pit_dataset(dataset: object) -> EdgeEvidenceVerification:
    """Re-prove a dataset by strict parse, EF-3 re-proof, record re-digest and full reassembly. Total: never raises."""

    return verify_edge_artifact_total(
        dataset,
        cls=HistoricalPitDataset,
        to_payload=_to_payload,
        parse_payload=historical_pit_dataset_from_payload,
        reassemble=_reassemble_dataset,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


# --- PIT view -----------------------------------------------------------------------------------------------------------


def select_visible_pit_records(
    dataset: HistoricalPitDataset, *, series_id: str, instrument: str, decision_time_ns: int
) -> HistoricalPitView:
    """Pure PIT visibility over a dataset the caller has ALREADY verified intact, READY and advancing.

    Visible: ``available_at_ns <= t``; for a final-required series also ``finalized_at_ns is not None`` and
    ``finalized_at_ns <= t``; per logical record only the latest vintage available at ``t``. Ordered by event time,
    then sequence. Raises ``HistoricalPitDatasetError`` for an unknown series or a non-positive decision time.
    """

    if type(decision_time_ns) is not int or decision_time_ns <= 0 or decision_time_ns > _MAX_WIRE_INT:
        raise _fail("view_decision_time_ns_invalid")
    semantics = {item.series_id: item for item in dataset.series_semantics}
    series = semantics.get(series_id)
    if series is None:
        raise _fail("view_series_unknown")
    latest: dict[int, HistoricalPitRecord] = {}
    for record in dataset.records:
        if record.series_id != series_id or record.instrument != instrument:
            continue
        if record.available_at_ns > decision_time_ns:
            continue
        if series.final_required and (record.finalized_at_ns is None or record.finalized_at_ns > decision_time_ns):
            continue
        current = latest.get(record.sequence_id)
        if current is None or record.available_at_ns > current.available_at_ns:
            latest[record.sequence_id] = record
    visible = tuple(sorted(latest.values(), key=lambda item: (item.event_time_ns, item.sequence_id)))
    return HistoricalPitView(
        dataset_digest=dataset.dataset_digest,
        series_id=series_id,
        instrument=instrument,
        decision_time_ns=decision_time_ns,
        final_required=series.final_required,
        records=visible,
    )


def build_historical_pit_view(
    dataset: HistoricalPitDataset, *, series_id: str, instrument: str, decision_time_ns: int
) -> HistoricalPitView:
    """Verify the dataset (intact, READY, advancing) and return its PIT view; raises otherwise."""

    verification = verify_historical_pit_dataset(dataset)
    if not verification.intact or dataset.advances is not True:
        raise _fail("view_dataset_not_verified_advancing")
    return select_visible_pit_records(
        dataset, series_id=series_id, instrument=instrument, decision_time_ns=decision_time_ns
    )


__all__ = [
    "HISTORICAL_PIT_NON_CLAIM_FLAGS",
    "HistoricalPitDataset",
    "HistoricalPitDatasetError",
    "HistoricalPitRecord",
    "HistoricalPitSeriesSemantics",
    "HistoricalPitValue",
    "HistoricalPitView",
    "build_historical_pit_dataset",
    "build_historical_pit_record",
    "build_historical_pit_view",
    "historical_pit_dataset_digest",
    "historical_pit_dataset_from_payload",
    "historical_pit_dataset_payload_is_well_formed",
    "historical_pit_dataset_to_dict",
    "historical_pit_record_digest",
    "is_canonical_pit_decimal",
    "select_visible_pit_records",
    "verify_historical_pit_dataset",
]
