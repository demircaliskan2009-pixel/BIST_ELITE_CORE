"""Edge Factory EF-3: deterministic PIT-grade edge source packet evidence (the candidate's data/series manifest).

EF-3 is the second gate of ``docs/crypto_core/edge_factory_design.md``. It is the point-in-time DATA manifest of a
candidate and is deliberately distinct from ``crypto_core.strategy.source_packet`` (idea provenance), which EF-2 already
binds. It consumes the EF-2 intake -- the root anchor, which for EF-3 is also the immediate predecessor -- and a
``crypto_core.data.requirements.DataRequirementRegistry``, and records every input series of the candidate.

Contract:

* The PIT vocabulary is not forked. A series names a ``DataRequirementKey``; its ``event_time`` / ``available_at`` /
  ``finalized_at`` policies, finality policy, funding semantics and availability mode are copied from the re-proven
  registry and are never declared by the caller.
* Finality is structural. A series that includes unfinalized records, or whose registry funding semantics are
  ``predicted``, FAILs; a series revised without point-in-time vintages FAILs; unknown finality or unknown revision
  behaviour is ``NEEDS_EXTERNAL_FACTS``. No unfinalized series can reach a PASS packet, so none can feed features.
* Rights reuse the SourcePacket rights vocabulary and its rule: RESTRICTED data FAILs and never silently passes.
* Coverage. The EF-2 declared data requirements must equal the series keys; every key must exist in the registry with
  paper parity (the ``validation/pit_parity.py`` default). Packet instrument coverage is the intersection of every
  series' coverage (an instrument is covered only when every input series covers it) and must be non-empty.
* The EF-2 root is re-proven through ``verify_edge_idea_intake_evidence``, matched to the caller anchor, and must be
  READY + PASS with the same correlation id; a NEEDS_* root never advances. The registry is re-proven from one
  canonical snapshot: its public digest matches the anchor, it re-parses through ``data_requirement_registry_from_dict``
  and the re-parsed registry has the same public digest.
* ``status`` (integrity) and ``gate_verdict`` (outcome) stay separate exactly as in EF-2; only READY + PASS advances.
* Paper-only, deterministic, immutable, no clock/IO/network/venue fact, and every structural non-claim of EF-2.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
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
_DATA_REQUIREMENT_KEY_VALUES = frozenset(key.value for key in DataRequirementKey)
_RIGHTS_STATUS_VALUES = frozenset(status.value for status in SourcePacketRightsStatus)
_AVAILABILITY_MODE_VALUES = frozenset(mode.value for mode in DataAvailabilityMode)
_REGISTRY_POLICY_FIELDS = ("event_time_policy", "available_at_policy", "finalized_at_policy")
_REGISTRY_OPTIONAL_FIELDS = ("paper_observation_source", "finality_policy", "funding_semantics")
# Same scope vocabulary as EF-2 (see edge_idea_intake_evidence.py).
_BIST_PATTERN = re.compile(r"(?<![a-z0-9])(?:bist|borsa|matriks)|(?<![a-z0-9])kap(?![a-z0-9])", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:private_api|private_key|api_key|api_secret|credential|order_router|place_order|live_order"
    r"|real_order|order_id|auto_loop|shadow_live_execution|scheduler)"
    r"|(?<![a-z0-9])live(?![a-z0-9])",
    re.IGNORECASE,
)


class EdgeSourcePacketEvidenceError(RuntimeError):
    """Raised on malformed caller input or a forbidden BIST/live/private/order/scheduler token."""


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


_SERIES_RECORD_KEYS = frozenset(field.name for field in fields(EdgeSourceSeriesRecord))
_FINALITY_VALUES = frozenset(item.value for item in EdgeSeriesFinality)
_REVISION_POLICY_VALUES = frozenset(item.value for item in EdgeSeriesRevisionPolicy)


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
    expected_root_intake_digest: str
    verified_root_intake_digest: str
    declared_data_requirement_keys: tuple[str, ...]
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


_CONSTANT_FIELDS: tuple[tuple[str, str], ...] = (
    ("schema_version", _SCHEMA_VERSION),
    ("gate_id", _GATE_ID),
    ("predecessor_gate_id", _PREDECESSOR_GATE_ID),
    ("anchor_policy", _ANCHOR_POLICY),
    ("pit_policy_source", _PIT_POLICY_SOURCE),
    ("feature_input_finality_rule", _FEATURE_INPUT_FINALITY_RULE),
    ("rights_vocabulary", _RIGHTS_VOCABULARY),
    ("coverage_policy", _COVERAGE_POLICY),
)
_TEXT_FIELDS = ("packet_evidence_id", "correlation_id")
_SERIES_TEXT_FIELDS = ("series_id", "source_reference", "rights_reference")


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _is_plain_text(value: object) -> bool:
    return (
        type(value) is str
        and value != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _scope_violation(text: str) -> str | None:
    if _BIST_PATTERN.search(text):
        return "bist_scope_leakage"
    if _FORBIDDEN_PATTERN.search(text):
        return "forbidden_scope_token"
    return None


def _is_clean_text(value: object) -> bool:
    return _is_plain_text(value) and _scope_violation(value) is None  # type: ignore[arg-type]


def _require_text(value: object, field_name: str) -> str:
    if not _is_plain_text(value):
        raise EdgeSourcePacketEvidenceError(_reason(f"{field_name}_invalid"))
    violation = _scope_violation(value)  # type: ignore[arg-type]
    if violation is not None:
        raise EdgeSourcePacketEvidenceError(_reason(f"{violation}:{field_name}"))
    return value  # type: ignore[return-value]


def _is_canonical_reason_list(value: object) -> bool:
    return (
        type(value) is list
        and all(type(code) is str and code.startswith(f"{_REASON_PREFIX}:") for code in value)
        and value == sorted(set(value))
    )


def _is_canonical_key_list(value: object) -> bool:
    return (
        type(value) is list
        and bool(value)
        and value == sorted(set(value))
        and set(value) <= _DATA_REQUIREMENT_KEY_VALUES
    )


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


def _registry_proof(
    registry: DataRequirementRegistry, expected_digest: str
) -> tuple[list[str], DataRequirementRegistry | None]:
    """Re-prove the registry from ONE canonical snapshot: public digest, anchor, public re-parse, canonical form."""

    try:
        canonical = _canonical_json(data_requirement_registry_to_dict(registry))
        snapshot = json.loads(canonical)
    except Exception:  # noqa: BLE001 - a forged or non-serializable registry must fail closed, never crash
        return [_reason("data_requirement_registry_malformed_payload")], None
    failures: list[str] = []
    recomputed = _sha256(canonical)
    if recomputed != expected_digest:
        failures.append(_reason("data_requirement_registry_digest_mismatch"))
    try:
        result = data_requirement_registry_from_dict(snapshot)
    except Exception:  # noqa: BLE001 - the public parser refusing the snapshot is a rejection, never a crash
        result = None
    if result is None or result.accepted is not True or type(result.registry) is not DataRequirementRegistry:
        failures.append(_reason("data_requirement_registry_invalid"))
        return failures, None
    if data_requirement_registry_digest(result.registry) != recomputed:
        failures.append(_reason("data_requirement_registry_noncanonical"))
    return failures, result.registry


def _consume_root_intake(
    verification: EdgeEvidenceVerification, expected_digest: str, correlation_id: str
) -> tuple[list[str], dict[str, object] | None]:
    if not verification.intact:
        return [_reason(f"root_intake_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != expected_digest:
        return [_reason("root_intake_digest_mismatch")], None
    snapshot = json.loads(verification.canonical_json)
    failures: list[str] = []
    if (
        snapshot["status"] != EdgeEvidenceStatus.READY.value
        or snapshot["gate_verdict"] != EdgeGateVerdict.PASS.value
        or snapshot["advances"] is not True
    ):
        failures.append(_reason(f"root_intake_not_passed:{snapshot['gate_verdict']}"))
    if snapshot["correlation_id"] != correlation_id:
        failures.append(_reason("correlation_id_mismatch"))
    return failures, snapshot


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


def _coverage_intersection(series: Sequence[Mapping[str, object]]) -> list[str]:
    common = set(series[0]["instrument_coverage"])  # type: ignore[call-overload]
    for record in series[1:]:
        common &= set(record["instrument_coverage"])  # type: ignore[call-overload]
    return sorted(common)


def _packet_verdict_reasons(
    *,
    declared_keys: Sequence[str],
    registry_keys: Sequence[str],
    series: Sequence[Mapping[str, object]],
    coverage: Sequence[str],
) -> tuple[list[str], list[str], list[str]]:
    fail: list[str] = []
    needs_external: list[str] = []
    series_keys = {record["data_requirement_key"] for record in series}
    fail.extend(
        _reason(f"declared_data_requirement_not_covered:{key}") for key in declared_keys if key not in series_keys
    )
    for record in series:
        series_id = record["series_id"]
        key = record["data_requirement_key"]
        if key not in declared_keys:
            fail.append(_reason(f"series_data_requirement_not_declared_in_intake:{series_id}"))
        if key not in registry_keys:
            fail.append(_reason(f"series_data_requirement_not_in_registry:{series_id}"))
        else:
            if (
                record["availability_mode"] != DataAvailabilityMode.PAPER_PARITY.value
                or record["paper_observation_source"] is None
            ):
                fail.append(_reason(f"series_paper_parity_unavailable:{series_id}"))
            if record["funding_semantics"] == _PREDICTED_FUNDING_SEMANTICS:
                fail.append(_reason(f"series_funding_semantics_predicted_unfinalized:{series_id}"))
        if record["rights_status"] == SourcePacketRightsStatus.RESTRICTED.value:
            fail.append(_reason(f"series_rights_restricted:{series_id}"))
        if record["finality"] == EdgeSeriesFinality.INCLUDES_UNFINALIZED.value:
            fail.append(_reason(f"series_unfinalized_feature_input:{series_id}"))
        elif record["finality"] == EdgeSeriesFinality.UNKNOWN.value:
            needs_external.append(_reason(f"series_finality_unknown:{series_id}"))
        if record["revision_policy"] == EdgeSeriesRevisionPolicy.REVISED_WITHOUT_VINTAGES.value:
            fail.append(_reason(f"series_revised_without_point_in_time_vintages:{series_id}"))
        elif record["revision_policy"] == EdgeSeriesRevisionPolicy.UNKNOWN.value:
            needs_external.append(_reason(f"series_revision_policy_unknown:{series_id}"))
    if not coverage:
        fail.append(_reason("packet_instrument_coverage_empty"))
    return fail, needs_external, []


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
    if not _is_hex64(expected_root_intake_digest):
        raise EdgeSourcePacketEvidenceError(_reason("expected_root_intake_digest_invalid"))
    if type(data_requirement_registry) is not DataRequirementRegistry:
        raise EdgeSourcePacketEvidenceError(_reason("data_requirement_registry_malformed"))
    if not _is_hex64(expected_data_requirement_registry_digest):
        raise EdgeSourcePacketEvidenceError(_reason("expected_data_requirement_registry_digest_invalid"))
    packet_evidence_id = _require_text(packet_evidence_id, "packet_evidence_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    inputs = _canonical_series(series)

    root_failures, intake_snapshot = _consume_root_intake(
        verify_edge_idea_intake_evidence(intake), expected_root_intake_digest, correlation_id
    )
    registry_failures, registry = _registry_proof(data_requirement_registry, expected_data_requirement_registry_digest)
    integrity = _sorted_unique(root_failures + registry_failures)

    declared = None if intake_snapshot is None else intake_snapshot.get("data_requirement_keys")
    declared_keys = tuple(declared) if _is_canonical_key_list(declared) else ()  # type: ignore[arg-type]
    registry_keys = () if registry is None else tuple(sorted(key.value for key in registry.requirements))
    records = tuple(_series_record(item, registry) for item in inputs)
    record_payloads = [_serialize(record) for record in records]
    coverage = tuple(_coverage_intersection(record_payloads))  # type: ignore[arg-type]

    if integrity:
        status = EdgeEvidenceStatus.REJECTED
        verdict = EdgeGateVerdict.NOT_EVALUATED
        verdict_reasons: tuple[str, ...] = ()
        verified_root_intake_digest = ""
        verified_registry_digest = ""
    else:
        fail, needs_external, needs_governance = _packet_verdict_reasons(
            declared_keys=declared_keys,
            registry_keys=registry_keys,
            series=record_payloads,  # type: ignore[arg-type]
            coverage=coverage,
        )
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)
        verified_root_intake_digest = expected_root_intake_digest
        verified_registry_digest = expected_data_requirement_registry_digest

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
        expected_root_intake_digest=expected_root_intake_digest,
        verified_root_intake_digest=verified_root_intake_digest,
        declared_data_requirement_keys=declared_keys,
        expected_data_requirement_registry_digest=expected_data_requirement_registry_digest,
        verified_data_requirement_registry_digest=verified_registry_digest,
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
    return replace(seed, packet_evidence_digest=edge_source_packet_evidence_digest(seed))


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


def _envelope_failures(body: Mapping[str, object]) -> list[str]:
    failures: list[str] = []
    if any(body.get(name) != expected for name, expected in _CONSTANT_FIELDS):
        failures.append(_reason("constant_field_mismatch"))
    if any(body.get(name) is not expected for name, expected in EDGE_STRUCTURAL_NON_CLAIM_FLAGS):
        failures.append(_reason("structural_non_claim_violation"))
    integrity = body.get("integrity_reason_codes")
    verdict_codes = body.get("verdict_reason_codes")
    if not _is_canonical_reason_list(integrity) or not _is_canonical_reason_list(verdict_codes):
        failures.append(_reason("reason_codes_noncanonical"))
    status = body.get("status")
    verdict = body.get("gate_verdict")
    if status == EdgeEvidenceStatus.READY.value:
        coherent = verdict != EdgeGateVerdict.NOT_EVALUATED.value and integrity == []
    elif status == EdgeEvidenceStatus.REJECTED.value:
        coherent = verdict == EdgeGateVerdict.NOT_EVALUATED.value and bool(integrity) and verdict_codes == []
    else:
        coherent = False
    advances = status == EdgeEvidenceStatus.READY.value and verdict == EdgeGateVerdict.PASS.value
    if not coherent or body.get("advances") is not advances:
        failures.append(_reason("status_verdict_incoherent"))
    return failures


def _is_text(value: object) -> bool:
    """Presence check for registry-owned text, whose canonical form belongs to ``data/requirements.py``."""

    return type(value) is str and value != ""


def _is_valid_series_record(record: object, registry_keys: Sequence[str]) -> bool:
    if type(record) is not dict or set(record) != _SERIES_RECORD_KEYS:
        return False
    coverage = record["instrument_coverage"]
    if (
        any(not _is_clean_text(record[name]) for name in _SERIES_TEXT_FIELDS)
        or record["data_requirement_key"] not in _DATA_REQUIREMENT_KEY_VALUES
        or record["rights_status"] not in _RIGHTS_STATUS_VALUES
        or record["finality"] not in _FINALITY_VALUES
        or record["revision_policy"] not in _REVISION_POLICY_VALUES
        or type(coverage) is not list
        or not coverage
        or coverage != sorted(set(coverage))
        or any(not _is_clean_text(symbol) for symbol in coverage)
    ):
        return False
    if record["data_requirement_key"] in registry_keys:
        return (
            record["availability_mode"] in _AVAILABILITY_MODE_VALUES
            and all(_is_text(record[name]) for name in _REGISTRY_POLICY_FIELDS)
            and all(record[name] is None or _is_text(record[name]) for name in _REGISTRY_OPTIONAL_FIELDS)
        )
    return (
        record["availability_mode"] == ""
        and all(record[name] == "" for name in _REGISTRY_POLICY_FIELDS)
        and all(record[name] is None for name in _REGISTRY_OPTIONAL_FIELDS)
    )


def _packet_semantic_failures(body: Mapping[str, object]) -> list[str]:
    failures: list[str] = []
    for name in _TEXT_FIELDS:
        if not _is_clean_text(body.get(name)):
            failures.append(_reason(f"text_field_invalid:{name}"))
    for expected_name, verified_name in (
        ("expected_root_intake_digest", "verified_root_intake_digest"),
        ("expected_data_requirement_registry_digest", "verified_data_requirement_registry_digest"),
    ):
        if not _is_hex64(body.get(expected_name)) or body.get(verified_name) != body.get(expected_name):
            failures.append(_reason(f"verified_digest_mismatch:{verified_name}"))
    declared_keys = body.get("declared_data_requirement_keys")
    registry_keys = body.get("registry_keys")
    if not _is_canonical_key_list(declared_keys) or not _is_canonical_key_list(registry_keys):
        failures.append(_reason("data_requirement_keys_noncanonical"))
        return failures
    if not _is_text(body.get("data_requirement_registry_schema_version")):
        failures.append(_reason("data_requirement_registry_schema_version_invalid"))
    series = body.get("series")
    if (
        type(series) is not list
        or not series
        or any(not _is_valid_series_record(record, registry_keys) for record in series)  # type: ignore[arg-type]
        or [record["series_id"] for record in series] != sorted({record["series_id"] for record in series})
        or len({record["data_requirement_key"] for record in series}) != len(series)
    ):
        failures.append(_reason("series_noncanonical"))
        return failures
    coverage = _coverage_intersection(series)
    if body.get("packet_instrument_coverage") != coverage:
        failures.append(_reason("packet_instrument_coverage_mismatch"))
    fail, needs_external, needs_governance = _packet_verdict_reasons(
        declared_keys=declared_keys,  # type: ignore[arg-type]
        registry_keys=registry_keys,  # type: ignore[arg-type]
        series=series,
        coverage=coverage,
    )
    rederived = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
    if list(_sorted_unique(fail + needs_external + needs_governance)) != body.get(
        "verdict_reason_codes"
    ) or rederived.value != body.get("gate_verdict"):
        failures.append(_reason("verdict_rederivation_mismatch"))
    return failures


def verify_edge_source_packet_evidence(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove EF-3 packet evidence: exact type, self-digest, constants, non-claims, status/verdict coherence, and
    (when READY) the coverage and verdict re-derived from the carried series. Never raises on forged input."""

    if (
        type(evidence) is not EdgeSourcePacketEvidence
        or type(evidence.status) is not EdgeEvidenceStatus
        or type(evidence.gate_verdict) is not EdgeGateVerdict
    ):
        return EdgeEvidenceVerification(False, (_reason("evidence_type_invalid"),), "", "")
    try:
        canonical = _canonical_json(edge_source_packet_evidence_to_dict(evidence))
        snapshot = json.loads(canonical)
    except Exception:  # noqa: BLE001 - a forged or non-serializable artifact must fail closed, never crash
        return EdgeEvidenceVerification(False, (_reason("evidence_serialization_failed"),), "", "")
    body = dict(snapshot)
    carried = body.pop(_SELF_DIGEST_FIELD, None)
    recomputed = _sha256(_canonical_json(body))
    failures: list[str] = []
    if carried != recomputed:
        failures.append(_reason("self_digest_mismatch"))
    failures.extend(_envelope_failures(body))
    if body.get("status") == EdgeEvidenceStatus.READY.value:
        try:
            failures.extend(_packet_semantic_failures(body))
        except Exception:  # noqa: BLE001 - malformed carried semantics fail closed
            failures.append(_reason("evidence_semantics_malformed"))
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
    "edge_source_packet_evidence_to_dict",
    "verify_edge_source_packet_evidence",
]
