"""Edge Factory EF-3: deterministic PIT-grade edge source packet evidence (the candidate's data/series manifest).

EF-3 is the second gate of ``docs/crypto_core/edge_factory_design.md``. It is the point-in-time DATA manifest of a
candidate and is deliberately distinct from ``crypto_core.strategy.source_packet`` (idea provenance), which EF-2 already
binds. It consumes the EF-2 intake -- the root anchor, which for EF-3 is also the immediate predecessor -- and a
``crypto_core.data.requirements.DataRequirementRegistry``, and records every input series of the candidate.

Contract:

* Authority is carried, never copied. The artifact commits one canonical EF-2 snapshot and one canonical registry
  snapshot. The root is strictly reconstructed through ``edge_idea_intake_evidence_from_canonical_json``, re-proven by
  ``verify_edge_idea_intake_evidence``, matched to the caller root anchor, and must be READY + PASS with the same
  correlation id; the declared data requirements come from that authenticated root. The registry snapshot is parsed
  through ``data_requirement_registry_from_dict``, its digest matched to the caller anchor, and its public digest after
  re-parse must equal the snapshot digest.
* The PIT vocabulary is not forked. A series names a ``DataRequirementKey``; its ``event_time`` / ``available_at`` /
  ``finalized_at`` policies, finality policy, funding semantics and availability mode are derived from the
  authenticated registry for that exact key and are never declared by the caller.
* Finality is structural. A series that includes unfinalized records, or whose registry funding semantics are
  ``predicted``, FAILs; a series revised without point-in-time vintages FAILs; unknown finality or unknown revision
  behaviour is ``NEEDS_EXTERNAL_FACTS``. No unfinalized series can reach a PASS packet, so none can feed features.
* Rights reuse the SourcePacket rights vocabulary and its rule: RESTRICTED data FAILs and never silently passes.
* Coverage. The root's declared data requirements must equal the series keys; every key must exist in the registry with
  paper parity (the ``validation/pit_parity.py`` default). Packet instrument coverage is the intersection of every
  series' coverage and must be non-empty.
* Verification is reassembly: ``verify_edge_source_packet_evidence`` strictly parses the carried artifact, re-runs the
  one assembly path over its carried snapshots, anchors and series declarations, and requires field-for-field equality,
  for READY and REJECTED artifacts alike.
* ``status`` (integrity) and ``gate_verdict`` (outcome) stay separate exactly as in EF-2; only READY + PASS advances.
  Paper-only, deterministic, immutable, no clock/IO/network/venue fact, every structural non-claim of EF-2, and the
  single Edge Factory scope policy ``edge_scope_violation``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields
from enum import Enum

from crypto_core.data.requirements import (
    DataAvailabilityMode,
    DataRequirementKey,
    DataRequirementRegistry,
    data_requirement_registry_digest,
    data_requirement_registry_from_dict,
    data_requirement_registry_to_dict,
)
from crypto_core.strategy.source_packet import SourcePacketRightsStatus
from crypto_core.validation.edge_idea_intake_evidence import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    EdgeIdeaIntakeEvidence,
    edge_idea_intake_evidence_from_canonical_json,
    edge_idea_intake_evidence_to_dict,
    edge_scope_violation,
    resolve_edge_gate_verdict,
    verify_edge_idea_intake_evidence,
)

_SCHEMA_VERSION = "edge-source-packet-evidence.v1"
_GATE_ID = "EF-3"
_PREDECESSOR_GATE_ID = "EF-2"
_ANCHOR_POLICY = "ef2_root_intake_digest_is_also_the_immediate_predecessor.v1"
_PIT_POLICY_SOURCE = "crypto_core.data.requirements.DataRequirementRegistry"
_RIGHTS_VOCABULARY = "crypto_core.strategy.source_packet.SourcePacketRightsStatus"
_FEATURE_INPUT_FINALITY_RULE = "only_finalized_non_predicted_series_may_feed_features.v1"
_COVERAGE_POLICY = "intersection_of_every_series_instrument_coverage.v1"
_REASON_PREFIX = "edge_source_packet_evidence"
_SELF_DIGEST_FIELD = "packet_evidence_digest"
_PREDICTED_FUNDING_SEMANTICS = "predicted"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_FLAG_NAMES = frozenset(name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS)


class EdgeSourcePacketEvidenceError(RuntimeError):
    """Raised on malformed caller input, a malformed carried artifact, or a forbidden scope token."""


class EdgeSeriesFinality(str, Enum):
    """Whether an input series delivers only finalized records."""

    FINALIZED_ONLY = "finalized_only"
    INCLUDES_UNFINALIZED = "includes_unfinalized"
    UNKNOWN = "unknown"


class EdgeSeriesRevisionPolicy(str, Enum):
    """How an input series treats history after finalization."""

    IMMUTABLE_AFTER_FINALIZATION = "immutable_after_finalization"
    REVISED_WITH_POINT_IN_TIME_VINTAGES = "revised_with_point_in_time_vintages"
    REVISED_WITHOUT_VINTAGES = "revised_without_vintages"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EdgeInputSeries:
    """Caller declaration of one input series. PIT policies are not declared here; they come from the registry."""

    series_id: str
    data_requirement_key: DataRequirementKey
    source_reference: str
    rights_status: SourcePacketRightsStatus
    rights_reference: str
    finality: EdgeSeriesFinality
    revision_policy: EdgeSeriesRevisionPolicy
    instrument_coverage: tuple[str, ...]


@dataclass(frozen=True)
class EdgeSourceSeriesRecord:
    """One recorded input series: the caller declaration plus the registry-owned PIT semantics for its key."""

    series_id: str
    data_requirement_key: str
    source_reference: str
    rights_status: str
    rights_reference: str
    finality: str
    revision_policy: str
    instrument_coverage: tuple[str, ...]
    availability_mode: str
    paper_observation_source: str | None
    event_time_policy: str
    available_at_policy: str
    finalized_at_policy: str
    finality_policy: str | None
    funding_semantics: str | None


@dataclass(frozen=True)
class EdgeSourcePacketEvidence:
    """Immutable, digest-bound EF-3 PIT data manifest. PAPER ONLY; proves process survival, never an edge."""

    schema_version: str
    gate_id: str
    predecessor_gate_id: str
    anchor_policy: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    packet_evidence_id: str
    correlation_id: str
    root_intake_snapshot_json: str
    expected_root_intake_digest: str
    verified_root_intake_digest: str
    declared_data_requirement_keys: tuple[str, ...]
    data_requirement_registry_snapshot_json: str
    expected_data_requirement_registry_digest: str
    verified_data_requirement_registry_digest: str
    data_requirement_registry_schema_version: str
    registry_keys: tuple[str, ...]
    pit_policy_source: str
    feature_input_finality_rule: str
    rights_vocabulary: str
    coverage_policy: str
    series: tuple[EdgeSourceSeriesRecord, ...]
    packet_instrument_coverage: tuple[str, ...]
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    packet_evidence_digest: str
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


_SERIES_RECORD_KEYS = frozenset(field.name for field in fields(EdgeSourceSeriesRecord))
_SERIES_OPTIONAL_FIELDS = frozenset({"paper_observation_source", "finality_policy", "funding_semantics"})
_PACKET_FIELD_KINDS: dict[str, object] = {
    "status": EdgeEvidenceStatus,
    "gate_verdict": EdgeGateVerdict,
    "advances": "bool",
    "declared_data_requirement_keys": "str_tuple",
    "registry_keys": "str_tuple",
    "series": "series",
    "packet_instrument_coverage": "str_tuple",
    "integrity_reason_codes": "str_tuple",
    "verdict_reason_codes": "str_tuple",
    **dict.fromkeys(_FLAG_NAMES, "bool"),
}


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant {value}")


def _is_plain_text(value: object) -> bool:
    return (
        type(value) is str
        and value != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _require_text(value: object, field_name: str) -> str:
    if not _is_plain_text(value):
        raise EdgeSourcePacketEvidenceError(_reason(f"{field_name}_invalid"))
    violation = edge_scope_violation(value)  # type: ignore[arg-type]
    if violation is not None:
        raise EdgeSourcePacketEvidenceError(_reason(f"{violation}:{field_name}"))
    return value  # type: ignore[return-value]


def _safe_canonical_snapshot(to_dict: Callable[[object], object], value: object) -> str:
    try:
        return _canonical_json(to_dict(value))
    except Exception:  # noqa: BLE001 - an unserializable input is recorded as an empty snapshot and fails re-proof
        return ""


def _canonical_instruments(values: object) -> tuple[str, ...]:
    if type(values) not in (tuple, list):
        raise EdgeSourcePacketEvidenceError(_reason("instrument_coverage_malformed"))
    symbols: set[str] = set()
    for item in values:  # type: ignore[union-attr]
        symbol = _require_text(item, "instrument_symbol")
        if symbol in symbols:
            raise EdgeSourcePacketEvidenceError(_reason("instrument_symbol_duplicate"))
        symbols.add(symbol)
    if not symbols:
        raise EdgeSourcePacketEvidenceError(_reason("instrument_coverage_empty"))
    return tuple(sorted(symbols))


def _canonical_series(series: object) -> tuple[EdgeInputSeries, ...]:
    if type(series) not in (tuple, list):
        raise EdgeSourcePacketEvidenceError(_reason("series_malformed"))
    by_id: dict[str, EdgeInputSeries] = {}
    keys: set[DataRequirementKey] = set()
    for item in series:  # type: ignore[union-attr]
        if type(item) is not EdgeInputSeries:
            raise EdgeSourcePacketEvidenceError(_reason("series_item_malformed"))
        series_id = _require_text(item.series_id, "series_id")
        if type(item.data_requirement_key) is not DataRequirementKey:
            raise EdgeSourcePacketEvidenceError(_reason("series_data_requirement_key_invalid"))
        if type(item.rights_status) is not SourcePacketRightsStatus:
            raise EdgeSourcePacketEvidenceError(_reason("series_rights_status_invalid"))
        if type(item.finality) is not EdgeSeriesFinality:
            raise EdgeSourcePacketEvidenceError(_reason("series_finality_invalid"))
        if type(item.revision_policy) is not EdgeSeriesRevisionPolicy:
            raise EdgeSourcePacketEvidenceError(_reason("series_revision_policy_invalid"))
        if series_id in by_id:
            raise EdgeSourcePacketEvidenceError(_reason("series_id_duplicate"))
        if item.data_requirement_key in keys:
            raise EdgeSourcePacketEvidenceError(_reason("series_data_requirement_key_duplicate"))
        keys.add(item.data_requirement_key)
        by_id[series_id] = EdgeInputSeries(
            series_id=series_id,
            data_requirement_key=item.data_requirement_key,
            source_reference=_require_text(item.source_reference, "series_source_reference"),
            rights_status=item.rights_status,
            rights_reference=_require_text(item.rights_reference, "series_rights_reference"),
            finality=item.finality,
            revision_policy=item.revision_policy,
            instrument_coverage=_canonical_instruments(item.instrument_coverage),
        )
    if not by_id:
        raise EdgeSourcePacketEvidenceError(_reason("series_empty"))
    return tuple(by_id[series_id] for series_id in sorted(by_id))


def _root_authority(
    snapshot_json: str, expected_digest: str, correlation_id: str
) -> tuple[list[str], EdgeIdeaIntakeEvidence | None]:
    """Reconstruct and re-prove the carried EF-2 root; root-owned values come only from this authenticated root."""

    try:
        root = edge_idea_intake_evidence_from_canonical_json(snapshot_json)
    except Exception:  # noqa: BLE001 - an unparseable root snapshot is a rejection, never a crash
        return [_reason("root_intake_malformed_payload")], None
    verification = verify_edge_idea_intake_evidence(root)
    if not verification.intact:
        return [_reason(f"root_intake_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != expected_digest:
        return [_reason("root_intake_digest_mismatch")], None
    codes: list[str] = []
    if (
        root.status is not EdgeEvidenceStatus.READY
        or root.gate_verdict is not EdgeGateVerdict.PASS
        or root.advances is not True
    ):
        codes.append(_reason(f"root_intake_not_passed:{root.gate_verdict.value}"))
    if root.correlation_id != correlation_id:
        codes.append(_reason("correlation_id_mismatch"))
    return codes, root


def _registry_authority(snapshot_json: str, expected_digest: str) -> tuple[list[str], DataRequirementRegistry | None]:
    """Re-prove the carried registry snapshot through the public registry parser, serializer and digest."""

    try:
        payload = json.loads(snapshot_json, parse_constant=_reject_json_constant)
    except Exception:  # noqa: BLE001 - an unparseable registry snapshot is a rejection, never a crash
        return [_reason("data_requirement_registry_malformed_payload")], None
    if type(payload) is not dict:
        return [_reason("data_requirement_registry_malformed_payload")], None
    codes: list[str] = []
    if _canonical_json(payload) != snapshot_json:
        codes.append(_reason("data_requirement_registry_snapshot_noncanonical"))
    recomputed = _sha256(snapshot_json)
    if recomputed != expected_digest:
        codes.append(_reason("data_requirement_registry_digest_mismatch"))
    try:
        result = data_requirement_registry_from_dict(payload)
    except Exception:  # noqa: BLE001 - the public parser refusing the snapshot is a rejection, never a crash
        result = None
    if result is None or result.accepted is not True or type(result.registry) is not DataRequirementRegistry:
        return [*codes, _reason("data_requirement_registry_invalid")], None
    if data_requirement_registry_digest(result.registry) != recomputed:
        codes.append(_reason("data_requirement_registry_noncanonical"))
    return codes, result.registry


def _series_record(item: EdgeInputSeries, registry: DataRequirementRegistry | None) -> EdgeSourceSeriesRecord:
    requirement = None if registry is None else registry.requirements.get(item.data_requirement_key)
    return EdgeSourceSeriesRecord(
        series_id=item.series_id,
        data_requirement_key=item.data_requirement_key.value,
        source_reference=item.source_reference,
        rights_status=item.rights_status.value,
        rights_reference=item.rights_reference,
        finality=item.finality.value,
        revision_policy=item.revision_policy.value,
        instrument_coverage=item.instrument_coverage,
        availability_mode="" if requirement is None else requirement.availability_mode.value,
        paper_observation_source=None if requirement is None else requirement.paper_observation_source,
        event_time_policy="" if requirement is None else requirement.event_time_policy,
        available_at_policy="" if requirement is None else requirement.available_at_policy,
        finalized_at_policy="" if requirement is None else requirement.finalized_at_policy,
        finality_policy=None if requirement is None else requirement.finality_policy,
        funding_semantics=None if requirement is None else requirement.funding_semantics,
    )


def _packet_verdict_reasons(
    *,
    declared_keys: Sequence[str],
    registry_keys: Sequence[str],
    series: Sequence[EdgeSourceSeriesRecord],
    coverage: Sequence[str],
) -> tuple[list[str], list[str], list[str]]:
    fail: list[str] = []
    needs_external: list[str] = []
    series_keys = {record.data_requirement_key for record in series}
    fail.extend(
        _reason(f"declared_data_requirement_not_covered:{key}") for key in declared_keys if key not in series_keys
    )
    for record in series:
        series_id = record.series_id
        if record.data_requirement_key not in declared_keys:
            fail.append(_reason(f"series_data_requirement_not_declared_in_intake:{series_id}"))
        if record.data_requirement_key not in registry_keys:
            fail.append(_reason(f"series_data_requirement_not_in_registry:{series_id}"))
        else:
            if (
                record.availability_mode != DataAvailabilityMode.PAPER_PARITY.value
                or record.paper_observation_source is None
            ):
                fail.append(_reason(f"series_paper_parity_unavailable:{series_id}"))
            if record.funding_semantics == _PREDICTED_FUNDING_SEMANTICS:
                fail.append(_reason(f"series_funding_semantics_predicted_unfinalized:{series_id}"))
        if record.rights_status == SourcePacketRightsStatus.RESTRICTED.value:
            fail.append(_reason(f"series_rights_restricted:{series_id}"))
        if record.finality == EdgeSeriesFinality.INCLUDES_UNFINALIZED.value:
            fail.append(_reason(f"series_unfinalized_feature_input:{series_id}"))
        elif record.finality == EdgeSeriesFinality.UNKNOWN.value:
            needs_external.append(_reason(f"series_finality_unknown:{series_id}"))
        if record.revision_policy == EdgeSeriesRevisionPolicy.REVISED_WITHOUT_VINTAGES.value:
            fail.append(_reason(f"series_revised_without_point_in_time_vintages:{series_id}"))
        elif record.revision_policy == EdgeSeriesRevisionPolicy.UNKNOWN.value:
            needs_external.append(_reason(f"series_revision_policy_unknown:{series_id}"))
    if not coverage:
        fail.append(_reason("packet_instrument_coverage_empty"))
    return fail, needs_external, []


def _assemble_packet(
    *,
    root_intake_snapshot_json: object,
    expected_root_intake_digest: object,
    data_requirement_registry_snapshot_json: object,
    expected_data_requirement_registry_digest: object,
    series: object,
    packet_evidence_id: object,
    correlation_id: object,
) -> EdgeSourcePacketEvidence:
    """The one assembly path of EF-3, shared by the builder and by reassembly-based verification."""

    if type(root_intake_snapshot_json) is not str or type(data_requirement_registry_snapshot_json) is not str:
        raise EdgeSourcePacketEvidenceError(_reason("authority_snapshot_malformed"))
    if not _is_hex64(expected_root_intake_digest):
        raise EdgeSourcePacketEvidenceError(_reason("expected_root_intake_digest_invalid"))
    if not _is_hex64(expected_data_requirement_registry_digest):
        raise EdgeSourcePacketEvidenceError(_reason("expected_data_requirement_registry_digest_invalid"))
    packet_evidence_id = _require_text(packet_evidence_id, "packet_evidence_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    inputs = _canonical_series(series)

    root_codes, root = _root_authority(root_intake_snapshot_json, expected_root_intake_digest, correlation_id)  # type: ignore[arg-type]
    registry_codes, registry = _registry_authority(
        data_requirement_registry_snapshot_json,
        expected_data_requirement_registry_digest,  # type: ignore[arg-type]
    )
    integrity = _sorted_unique(root_codes + registry_codes)

    declared_keys = () if root is None else root.data_requirement_keys
    registry_keys = () if registry is None else tuple(sorted(key.value for key in registry.requirements))
    records = tuple(_series_record(item, registry) for item in inputs)
    common = set(records[0].instrument_coverage)
    for record in records[1:]:
        common &= set(record.instrument_coverage)
    coverage = tuple(sorted(common))

    if integrity:
        status = EdgeEvidenceStatus.REJECTED
        verdict = EdgeGateVerdict.NOT_EVALUATED
        verdict_reasons: tuple[str, ...] = ()
    else:
        fail, needs_external, needs_governance = _packet_verdict_reasons(
            declared_keys=declared_keys, registry_keys=registry_keys, series=records, coverage=coverage
        )
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    seed = EdgeSourcePacketEvidence(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        predecessor_gate_id=_PREDECESSOR_GATE_ID,
        anchor_policy=_ANCHOR_POLICY,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        packet_evidence_id=packet_evidence_id,
        correlation_id=correlation_id,
        root_intake_snapshot_json=root_intake_snapshot_json,
        expected_root_intake_digest=expected_root_intake_digest,  # type: ignore[arg-type]
        verified_root_intake_digest="" if integrity else expected_root_intake_digest,  # type: ignore[arg-type]
        declared_data_requirement_keys=declared_keys,
        data_requirement_registry_snapshot_json=data_requirement_registry_snapshot_json,
        expected_data_requirement_registry_digest=expected_data_requirement_registry_digest,  # type: ignore[arg-type]
        verified_data_requirement_registry_digest="" if integrity else expected_data_requirement_registry_digest,  # type: ignore[arg-type]
        data_requirement_registry_schema_version="" if registry is None else registry.schema_version,
        registry_keys=registry_keys,
        pit_policy_source=_PIT_POLICY_SOURCE,
        feature_input_finality_rule=_FEATURE_INPUT_FINALITY_RULE,
        rights_vocabulary=_RIGHTS_VOCABULARY,
        coverage_policy=_COVERAGE_POLICY,
        series=records,
        packet_instrument_coverage=coverage,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        packet_evidence_digest="",
    )
    return _with_digest(seed)


def _with_digest(seed: EdgeSourcePacketEvidence) -> EdgeSourcePacketEvidence:
    values = {field.name: getattr(seed, field.name) for field in fields(seed)}
    values[_SELF_DIGEST_FIELD] = edge_source_packet_evidence_digest(seed)
    return EdgeSourcePacketEvidence(**values)  # type: ignore[arg-type]


def build_edge_source_packet_evidence(
    intake: EdgeIdeaIntakeEvidence,
    *,
    expected_root_intake_digest: str,
    data_requirement_registry: DataRequirementRegistry,
    expected_data_requirement_registry_digest: str,
    series: Sequence[EdgeInputSeries],
    packet_evidence_id: str,
    correlation_id: str,
) -> EdgeSourcePacketEvidence:
    """Build deterministic EF-3 PIT data-manifest evidence over a re-proven EF-2 root and registry.

    Malformed caller input raises ``EdgeSourcePacketEvidenceError``. A root or registry that fails re-proof, or a root
    that is not READY + PASS, yields ``REJECTED`` / ``NOT_EVALUATED``. Otherwise the evidence is ``READY`` with a
    ``FAIL``, ``NEEDS_EXTERNAL_FACTS`` or ``PASS`` verdict.
    """

    if type(intake) is not EdgeIdeaIntakeEvidence:
        raise EdgeSourcePacketEvidenceError(_reason("root_intake_malformed"))
    if type(data_requirement_registry) is not DataRequirementRegistry:
        raise EdgeSourcePacketEvidenceError(_reason("data_requirement_registry_malformed"))
    return _assemble_packet(
        root_intake_snapshot_json=_safe_canonical_snapshot(edge_idea_intake_evidence_to_dict, intake),  # type: ignore[arg-type]
        expected_root_intake_digest=expected_root_intake_digest,
        data_requirement_registry_snapshot_json=_safe_canonical_snapshot(
            data_requirement_registry_to_dict,  # type: ignore[arg-type]
            data_requirement_registry,
        ),
        expected_data_requirement_registry_digest=expected_data_requirement_registry_digest,
        series=series,
        packet_evidence_id=packet_evidence_id,
        correlation_id=correlation_id,
    )


def _serialize(value: object) -> object:
    if type(value) is EdgeSourceSeriesRecord:
        return {field.name: _serialize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def edge_source_packet_evidence_to_dict(evidence: EdgeSourcePacketEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-3 packet evidence, including its self-digest."""

    return {field.name: _serialize(getattr(evidence, field.name)) for field in fields(evidence)}


def edge_source_packet_evidence_digest(evidence: EdgeSourcePacketEvidence) -> str:
    """Recompute the canonical packet evidence digest, excluding only the self-digest field."""

    payload = edge_source_packet_evidence_to_dict(evidence)
    del payload[_SELF_DIGEST_FIELD]
    return _sha256(_canonical_json(payload))


def _malformed() -> EdgeSourcePacketEvidenceError:
    return EdgeSourcePacketEvidenceError(_reason("packet_snapshot_malformed"))


def _parse_series_record(value: object) -> EdgeSourceSeriesRecord:
    if type(value) is not dict or set(value) != _SERIES_RECORD_KEYS:
        raise _malformed()
    for name, item in value.items():
        if name == "instrument_coverage":
            valid = type(item) is list and all(type(symbol) is str for symbol in item)
        elif name in _SERIES_OPTIONAL_FIELDS:
            valid = item is None or type(item) is str
        else:
            valid = type(item) is str
        if not valid:
            raise _malformed()
    return EdgeSourceSeriesRecord(**{**value, "instrument_coverage": tuple(value["instrument_coverage"])})


def _parse_field(kind: object, value: object) -> object:
    if kind == "bool":
        if type(value) is not bool:
            raise _malformed()
        return value
    if kind == "str_tuple":
        if type(value) is not list or any(type(item) is not str for item in value):
            raise _malformed()
        return tuple(value)
    if kind == "series":
        if type(value) is not list:
            raise _malformed()
        return tuple(_parse_series_record(item) for item in value)
    if isinstance(kind, type) and issubclass(kind, Enum):
        if type(value) is not str:
            raise _malformed()
        try:
            return kind(value)
        except ValueError as exc:
            raise _malformed() from exc
    if type(value) is not str:
        raise _malformed()
    return value


def edge_source_packet_evidence_from_canonical_json(text: str) -> EdgeSourcePacketEvidence:
    """Strictly reconstruct EF-3 evidence from its canonical JSON (exact fields and types, canonical reserialization).

    Reconstruction is not verification: downstream gates call ``verify_edge_source_packet_evidence`` on the result.
    """

    if type(text) is not str:
        raise _malformed()
    try:
        payload = json.loads(text, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise _malformed() from exc
    names = [field.name for field in fields(EdgeSourcePacketEvidence)]
    if type(payload) is not dict or set(payload) != set(names) or _canonical_json(payload) != text:
        raise _malformed()
    evidence = EdgeSourcePacketEvidence(
        **{name: _parse_field(_PACKET_FIELD_KINDS.get(name, "str"), payload[name]) for name in names}  # type: ignore[arg-type]
    )
    if _canonical_json(edge_source_packet_evidence_to_dict(evidence)) != text:
        raise _malformed()
    return evidence


def _reassemble_packet(evidence: EdgeSourcePacketEvidence) -> EdgeSourcePacketEvidence:
    series = tuple(
        EdgeInputSeries(
            series_id=record.series_id,
            data_requirement_key=DataRequirementKey(record.data_requirement_key),
            source_reference=record.source_reference,
            rights_status=SourcePacketRightsStatus(record.rights_status),
            rights_reference=record.rights_reference,
            finality=EdgeSeriesFinality(record.finality),
            revision_policy=EdgeSeriesRevisionPolicy(record.revision_policy),
            instrument_coverage=record.instrument_coverage,
        )
        for record in evidence.series
    )
    return _assemble_packet(
        root_intake_snapshot_json=evidence.root_intake_snapshot_json,
        expected_root_intake_digest=evidence.expected_root_intake_digest,
        data_requirement_registry_snapshot_json=evidence.data_requirement_registry_snapshot_json,
        expected_data_requirement_registry_digest=evidence.expected_data_requirement_registry_digest,
        series=series,
        packet_evidence_id=evidence.packet_evidence_id,
        correlation_id=evidence.correlation_id,
    )


def verify_edge_source_packet_evidence(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove EF-3 evidence by strict parse and reassembly from its carried root and registry snapshots, anchors and
    series declarations. READY and REJECTED artifacts alike must match field for field. Never raises."""

    if (
        type(evidence) is not EdgeSourcePacketEvidence
        or type(evidence.status) is not EdgeEvidenceStatus
        or type(evidence.gate_verdict) is not EdgeGateVerdict
    ):
        return EdgeEvidenceVerification(False, (_reason("evidence_type_invalid"),), "", "")
    try:
        canonical = _canonical_json(edge_source_packet_evidence_to_dict(evidence))
    except Exception:  # noqa: BLE001 - a forged or non-serializable artifact must fail closed, never crash
        return EdgeEvidenceVerification(False, (_reason("evidence_serialization_failed"),), "", "")
    carried_payload = json.loads(canonical)
    body = dict(carried_payload)
    carried_digest = body.pop(_SELF_DIGEST_FIELD)
    recomputed = _sha256(_canonical_json(body))
    failures: list[str] = []
    if carried_digest != recomputed:
        failures.append(_reason("self_digest_mismatch"))
    try:
        expected_payload = edge_source_packet_evidence_to_dict(
            _reassemble_packet(edge_source_packet_evidence_from_canonical_json(canonical))
        )
    except Exception:  # noqa: BLE001 - carried semantics that cannot be reassembled fail closed, never crash
        failures.append(_reason("evidence_semantics_malformed"))
    else:
        failures.extend(
            _reason(f"field_mismatch:{name}")
            for name in sorted(expected_payload)
            if _canonical_json(expected_payload[name]) != _canonical_json(carried_payload.get(name))
        )
    codes = _sorted_unique(failures)
    return EdgeEvidenceVerification(
        intact=not codes, reason_codes=codes, recomputed_digest=recomputed, canonical_json=canonical
    )


__all__ = [
    "EdgeInputSeries",
    "EdgeSeriesFinality",
    "EdgeSeriesRevisionPolicy",
    "EdgeSourcePacketEvidence",
    "EdgeSourcePacketEvidenceError",
    "EdgeSourceSeriesRecord",
    "build_edge_source_packet_evidence",
    "edge_source_packet_evidence_digest",
    "edge_source_packet_evidence_from_canonical_json",
    "edge_source_packet_evidence_to_dict",
    "verify_edge_source_packet_evidence",
]
