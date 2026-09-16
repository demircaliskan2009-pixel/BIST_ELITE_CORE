"""Edge Factory EF-3: deterministic point-in-time data manifest over an authenticated EF-2 intake root.

EF-3 records every input series a candidate needs, bound to the accepted
``crypto_core.data.requirements.DataRequirementRegistry``: the caller declares only what the registry cannot know
(series identity, source and rights references, observed finality, revision policy, instrument coverage); every
registry-owned property (availability mode, paper observation source, event/available/finalized time policies,
funding/price/order-book/liquidation semantics, finality policy and cost/latency assumptions) is DERIVED from the
authenticated registry and never accepted from the caller.

Trust model (shared kernel ``edge_artifact_core``):

* The EF-2 root is a required ``EdgeAuthorityBinding`` whose snapshot must be a well-formed EF-2 payload. Assembly
  re-proves it through ``verify_edge_idea_intake_evidence``, requires the recomputed digest to equal the caller anchor
  and the root correlation to equal this manifest's correlation; an authentic REJECTED root receipt is never
  evaluated (integrity rejection).
* The registry is a required ``EdgeAuthorityBinding`` over the public ``data_requirement_registry_to_dict`` snapshot.
  Assembly re-proves it through the public ``data_requirement_registry_from_dict`` (accepted), canonical
  re-serialization and the public ``data_requirement_registry_digest`` against the caller anchor.
* An authentic authority that fails re-proof yields ``REJECTED``/``NOT_EVALUATED``; a malformed or non-serializable
  caller object is a construction error.
* PIT rule: a series is feature-input eligible only when it is registry-bound, paper-parity observable, rights-usable,
  finalized-only (declared, registry finality policy present, funding semantics not ``predicted``) and revision-safe
  (immutable after finalization or revised with point-in-time vintages). No unfinalized series is feature-ready.
* Only a READY + PASS root may advance; ``PASS`` here requires every series eligible, every intake data requirement
  covered, no series outside the intake, and a non-empty instrument coverage (per-requirement union, intersected
  across requirements). Unknown finality or revision policy is an external-fact need, never invented.
* One assembly path serves the builder and verifier reassembly; ``verify_edge_source_packet_evidence`` is total.
  Paper-only, deterministic, no IO/clock/network; every structural non-claim is a default no parameter can set.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum

from crypto_core.data.requirements import (
    DataAvailabilityMode,
    DataRequirement,
    DataRequirementKey,
    DataRequirementRegistry,
    data_requirement_registry_digest,
    data_requirement_registry_from_dict,
    data_requirement_registry_to_dict,
)
from crypto_core.strategy.source_packet import SourcePacketRightsStatus
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeArtifactError,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    build_edge_authority_binding,
    edge_authority_binding_snapshot,
    edge_authority_binding_to_payload,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    parse_edge_authority_binding,
    require_edge_authority_binding,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    EdgeIdeaIntakeEvidence,
    edge_idea_intake_evidence_from_payload,
    edge_idea_intake_evidence_payload_is_well_formed,
    edge_idea_intake_evidence_to_dict,
    verify_edge_idea_intake_evidence,
)

_SCHEMA_VERSION = "edge-source-packet-evidence.v2"
_GATE_ID = "EF-3"
_PREDECESSOR_GATE_ID = "EF-2"
_REASON_PREFIX = "edge_source_packet_evidence"
_SELF_DIGEST_FIELD = "source_packet_evidence_digest"
_FUNDING_SEMANTICS_UNFINALIZED = "predicted"
_INSTRUMENT_EXTRA_CHARS = frozenset("-_./:")
_FLAG_NAMES = frozenset(name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
_REGISTRY_KEYS = frozenset({"schema_version", "requirements"})
_REQUIREMENT_FIELDS = frozenset(field.name for field in fields(DataRequirement))
_REQUIREMENT_REQUIRED_TEXT_FIELDS = frozenset(
    {
        "key",
        "availability_mode",
        "historical_source",
        "event_time_policy",
        "available_at_policy",
        "finalized_at_policy",
        "fee_assumption",
        "slippage_assumption",
        "latency_assumption",
    }
)


class EdgeSourcePacketEvidenceError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


class EdgeSeriesFinality(str, Enum):
    """Caller-declared finality of the observed values of one series."""

    FINALIZED_ONLY = "finalized_only"
    INCLUDES_UNFINALIZED = "includes_unfinalized"
    UNKNOWN = "unknown"


class EdgeSeriesRevisionPolicy(str, Enum):
    """Caller-declared revision behaviour of one series after publication."""

    IMMUTABLE_AFTER_FINALIZATION = "immutable_after_finalization"
    REVISED_WITH_POINT_IN_TIME_VINTAGES = "revised_with_point_in_time_vintages"
    REVISED_WITHOUT_VINTAGES = "revised_without_vintages"
    UNKNOWN = "unknown"


_POINT_IN_TIME_REVISION_POLICIES = frozenset(
    {
        EdgeSeriesRevisionPolicy.IMMUTABLE_AFTER_FINALIZATION,
        EdgeSeriesRevisionPolicy.REVISED_WITH_POINT_IN_TIME_VINTAGES,
    }
)


@dataclass(frozen=True)
class EdgeInputSeries:
    """Caller declaration of one input series; registry-owned properties are deliberately absent."""

    series_id: str
    data_requirement_key: DataRequirementKey | str
    source_reference: str
    rights_status: SourcePacketRightsStatus | str
    rights_reference: str
    finality: EdgeSeriesFinality | str
    revision_policy: EdgeSeriesRevisionPolicy | str
    instrument_coverage: tuple[str, ...]


@dataclass(frozen=True)
class EdgeSourceSeriesRecord:
    """One manifest series: the declaration plus every registry-derived property and the derived PIT eligibility.

    Registry-derived fields are ``None`` exactly when ``registry_requirement_bound`` is False.
    """

    series_id: str
    data_requirement_key: str
    source_reference: str
    rights_status: str
    rights_reference: str
    finality: str
    revision_policy: str
    instrument_coverage: tuple[str, ...]
    registry_requirement_bound: bool
    availability_mode: str | None
    historical_source: str | None
    paper_observation_source: str | None
    event_time_policy: str | None
    available_at_policy: str | None
    finalized_at_policy: str | None
    funding_semantics: str | None
    price_semantics: str | None
    order_book_level: str | None
    order_book_depth: int | None
    sequence_policy: str | None
    resync_policy: str | None
    liquidation_source: str | None
    finality_policy: str | None
    fee_assumption: str | None
    slippage_assumption: str | None
    latency_assumption: str | None
    paper_parity_available: bool
    rights_usable: bool
    finalized_only: bool
    point_in_time_revision_safe: bool
    feature_input_eligible: bool


@dataclass(frozen=True)
class EdgeSourcePacketEvidence:
    """Immutable, digest-bound EF-3 point-in-time data manifest. PAPER ONLY; proves data discipline, never an edge."""

    schema_version: str
    gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    manifest_id: str
    correlation_id: str
    root_intake_binding: EdgeAuthorityBinding
    root_intake_digest: str
    predecessor_gate_id: str
    predecessor_digest: str
    candidate_strategy_id: str
    edge_family: str
    intake_data_requirement_keys: tuple[str, ...]
    data_requirement_registry_binding: EdgeAuthorityBinding
    data_requirement_registry_digest: str
    data_requirement_registry_schema_version: str
    series: tuple[EdgeSourceSeriesRecord, ...]
    instrument_coverage: tuple[str, ...]
    feature_input_series_ids: tuple[str, ...]
    regime_label_binding_status: str
    regime_evidence_status: str
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    source_packet_evidence_digest: str
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


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgeSourcePacketEvidenceError:
    return EdgeSourcePacketEvidenceError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _is_plain_text(value: object) -> bool:
    return (
        type(value) is str
        and value != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _require_text(value: object, field_name: str) -> str:
    if not _is_plain_text(value):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)  # type: ignore[arg-type]
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value  # type: ignore[return-value]


def _require_token(value: object, field_name: str) -> str:
    if type(value) is not str or not value or len(value) > 128 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail(f"{field_name}_invalid")
    if any(not (char.isascii() and (char.islower() or char.isdigit() or char in "_.:-")) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_instrument(value: object) -> str:
    if type(value) is not str or not value or len(value) > 64 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail("series_instrument_invalid")
    if any(not (char.isascii() and (char.isalnum() or char in _INSTRUMENT_EXTRA_CHARS)) for char in value):
        raise _fail("series_instrument_invalid")
    return _require_text(value, "series_instrument")


def _require_member(value: object, enum_cls: type[Enum], field_name: str) -> Enum:
    if type(value) is enum_cls:
        return value  # type: ignore[return-value]
    if type(value) is str:
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise _fail(f"{field_name}_invalid") from exc
    raise _fail(f"{field_name}_invalid")


# --- strict field conversion ----------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_optional_str(value: object) -> str | None:
    return None if value is None else _as_str(value)


def _as_optional_int(value: object) -> int | None:
    if value is not None and type(value) is not int:
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


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


def _serialize(value: object) -> object:
    if type(value) is EdgeAuthorityBinding:
        return edge_authority_binding_to_payload(value)
    if type(value) is EdgeSourceSeriesRecord:
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


# --- upstream authorities -------------------------------------------------------------------------------------------


def _registry_snapshot_is_well_formed(snapshot: object) -> bool:
    """Binding shape predicate: the exact structure ``data_requirement_registry_to_dict`` produces."""

    if type(snapshot) is not dict or set(snapshot) != _REGISTRY_KEYS or type(snapshot["schema_version"]) is not str:
        return False
    requirements = snapshot["requirements"]
    if type(requirements) is not dict or not requirements:
        return False
    for name, requirement in requirements.items():
        if type(name) is not str or type(requirement) is not dict or set(requirement) != _REQUIREMENT_FIELDS:
            return False
        for field_name, value in requirement.items():
            if field_name == "order_book_depth":
                valid = value is None or type(value) is int
            elif field_name in _REQUIREMENT_REQUIRED_TEXT_FIELDS:
                valid = type(value) is str
            else:
                valid = value is None or type(value) is str
            if not valid:
                return False
    return True


def _registry_authority(binding: EdgeAuthorityBinding) -> tuple[list[str], DataRequirementRegistry | None]:
    snapshot = edge_authority_binding_snapshot(binding)
    try:
        result = data_requirement_registry_from_dict(snapshot)
    except Exception:  # noqa: BLE001 - the public parser refusing authenticated fields is a truthful rejection
        result = None
    if result is None or result.accepted is not True or type(result.registry) is not DataRequirementRegistry:
        codes = [_reason("data_requirement_registry_not_accepted")]
        if edge_sha256_text(edge_canonical_json(snapshot)) != binding.expected_digest:
            codes.append(_reason("data_requirement_registry_digest_mismatch"))
        return codes, None
    registry = result.registry
    codes = []
    if data_requirement_registry_to_dict(registry) != snapshot:
        codes.append(_reason("data_requirement_registry_noncanonical"))
    if data_requirement_registry_digest(registry) != binding.expected_digest:
        codes.append(_reason("data_requirement_registry_digest_mismatch"))
    return codes, registry


def _root_intake_authority(
    binding: EdgeAuthorityBinding, correlation_id: str
) -> tuple[list[str], EdgeIdeaIntakeEvidence | None]:
    root = edge_idea_intake_evidence_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_idea_intake_evidence(root)
    if not verification.intact:
        return [_reason(f"root_intake_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("root_intake_digest_mismatch")], None
    if root.correlation_id != correlation_id:
        return [_reason("root_intake_correlation_mismatch")], None
    if root.status is not EdgeEvidenceStatus.READY:
        return [_reason("root_intake_rejected")], None
    return [], root


# --- series ---------------------------------------------------------------------------------------------------------


def _canonical_instruments(values: object) -> tuple[str, ...]:
    if type(values) not in (tuple, list):
        raise _fail("series_instrument_coverage_malformed")
    instruments: list[str] = []
    for item in values:  # type: ignore[union-attr]
        instrument = _require_instrument(item)
        if instrument in instruments:
            raise _fail("series_instrument_duplicate")
        instruments.append(instrument)
    if not instruments:
        raise _fail("series_instrument_coverage_empty")
    return tuple(sorted(instruments))


def _canonical_input_series(values: object) -> tuple[EdgeInputSeries, ...]:
    if type(values) not in (tuple, list):
        raise _fail("input_series_malformed")
    canonical: dict[str, EdgeInputSeries] = {}
    for item in values:  # type: ignore[union-attr]
        if type(item) is not EdgeInputSeries:
            raise _fail("input_series_entry_malformed")
        series_id = _require_token(item.series_id, "series_id")
        if series_id in canonical:
            raise _fail("series_id_duplicate")
        canonical[series_id] = EdgeInputSeries(
            series_id=series_id,
            data_requirement_key=_require_member(
                item.data_requirement_key, DataRequirementKey, "series_data_requirement_key"
            ),  # type: ignore[arg-type]
            source_reference=_require_text(item.source_reference, "series_source_reference"),
            rights_status=_require_member(item.rights_status, SourcePacketRightsStatus, "series_rights_status"),  # type: ignore[arg-type]
            rights_reference=_require_text(item.rights_reference, "series_rights_reference"),
            finality=_require_member(item.finality, EdgeSeriesFinality, "series_finality"),  # type: ignore[arg-type]
            revision_policy=_require_member(item.revision_policy, EdgeSeriesRevisionPolicy, "series_revision_policy"),  # type: ignore[arg-type]
            instrument_coverage=_canonical_instruments(item.instrument_coverage),
        )
    if not canonical:
        raise _fail("input_series_empty")
    return tuple(canonical[series_id] for series_id in sorted(canonical))


def _series_record(item: EdgeInputSeries, registry: DataRequirementRegistry | None) -> EdgeSourceSeriesRecord:
    requirement = None if registry is None else registry.requirements.get(item.data_requirement_key)  # type: ignore[arg-type]
    bound = requirement is not None
    paper_parity = (
        requirement is not None
        and requirement.availability_mode is DataAvailabilityMode.PAPER_PARITY
        and requirement.paper_observation_source is not None
    )
    finalized_only = (
        requirement is not None
        and item.finality is EdgeSeriesFinality.FINALIZED_ONLY
        and requirement.finality_policy is not None
        and requirement.funding_semantics != _FUNDING_SEMANTICS_UNFINALIZED
    )
    rights_usable = item.rights_status is not SourcePacketRightsStatus.RESTRICTED
    revision_safe = item.revision_policy in _POINT_IN_TIME_REVISION_POLICIES

    def derived(name: str) -> object:
        return None if requirement is None else getattr(requirement, name)

    return EdgeSourceSeriesRecord(
        series_id=item.series_id,
        data_requirement_key=item.data_requirement_key.value,  # type: ignore[union-attr]
        source_reference=item.source_reference,
        rights_status=item.rights_status.value,  # type: ignore[union-attr]
        rights_reference=item.rights_reference,
        finality=item.finality.value,  # type: ignore[union-attr]
        revision_policy=item.revision_policy.value,  # type: ignore[union-attr]
        instrument_coverage=item.instrument_coverage,
        registry_requirement_bound=bound,
        availability_mode=None if requirement is None else requirement.availability_mode.value,
        historical_source=derived("historical_source"),  # type: ignore[arg-type]
        paper_observation_source=derived("paper_observation_source"),  # type: ignore[arg-type]
        event_time_policy=derived("event_time_policy"),  # type: ignore[arg-type]
        available_at_policy=derived("available_at_policy"),  # type: ignore[arg-type]
        finalized_at_policy=derived("finalized_at_policy"),  # type: ignore[arg-type]
        funding_semantics=derived("funding_semantics"),  # type: ignore[arg-type]
        price_semantics=derived("price_semantics"),  # type: ignore[arg-type]
        order_book_level=derived("order_book_level"),  # type: ignore[arg-type]
        order_book_depth=derived("order_book_depth"),  # type: ignore[arg-type]
        sequence_policy=derived("sequence_policy"),  # type: ignore[arg-type]
        resync_policy=derived("resync_policy"),  # type: ignore[arg-type]
        liquidation_source=derived("liquidation_source"),  # type: ignore[arg-type]
        finality_policy=derived("finality_policy"),  # type: ignore[arg-type]
        fee_assumption=derived("fee_assumption"),  # type: ignore[arg-type]
        slippage_assumption=derived("slippage_assumption"),  # type: ignore[arg-type]
        latency_assumption=derived("latency_assumption"),  # type: ignore[arg-type]
        paper_parity_available=paper_parity,
        rights_usable=rights_usable,
        finalized_only=finalized_only,
        point_in_time_revision_safe=revision_safe,
        feature_input_eligible=bound and paper_parity and rights_usable and finalized_only and revision_safe,
    )


def _instrument_coverage(series: Sequence[EdgeInputSeries]) -> tuple[str, ...]:
    """Per data requirement the union of series coverage, intersected across requirements."""

    per_requirement: dict[str, set[str]] = {}
    for item in series:
        per_requirement.setdefault(item.data_requirement_key.value, set()).update(item.instrument_coverage)  # type: ignore[union-attr]
    covered = set.intersection(*per_requirement.values())
    return tuple(sorted(covered))


def _verdict_reasons(
    root: EdgeIdeaIntakeEvidence, records: Sequence[EdgeSourceSeriesRecord], coverage: Sequence[str]
) -> tuple[list[str], list[str]]:
    fail: list[str] = []
    needs_external: list[str] = []
    if root.advances is not True:
        fail.append(_reason("root_intake_not_advanced"))
    declared_keys = {record.data_requirement_key for record in records}
    fail.extend(
        _reason(f"intake_data_requirement_without_series:{key}")
        for key in root.data_requirement_keys
        if key not in declared_keys
    )
    for record in records:
        series_id = record.series_id
        if record.data_requirement_key not in root.data_requirement_keys:
            fail.append(_reason(f"series_data_requirement_not_in_intake:{series_id}"))
        if not record.registry_requirement_bound:
            fail.append(_reason(f"series_data_requirement_not_in_registry:{series_id}"))
        else:
            if not record.paper_parity_available:
                fail.append(_reason(f"series_paper_parity_unavailable:{series_id}"))
            if record.finality_policy is None:
                fail.append(_reason(f"series_registry_finality_policy_missing:{series_id}"))
            if record.funding_semantics == _FUNDING_SEMANTICS_UNFINALIZED:
                fail.append(_reason(f"series_registry_funding_semantics_unfinalized:{series_id}"))
        if not record.rights_usable:
            fail.append(_reason(f"series_rights_restricted:{series_id}"))
        if record.finality == EdgeSeriesFinality.INCLUDES_UNFINALIZED.value:
            fail.append(_reason(f"series_unfinalized:{series_id}"))
        elif record.finality == EdgeSeriesFinality.UNKNOWN.value:
            needs_external.append(_reason(f"series_finality_unknown:{series_id}"))
        if record.revision_policy == EdgeSeriesRevisionPolicy.REVISED_WITHOUT_VINTAGES.value:
            fail.append(_reason(f"series_revision_without_point_in_time_vintages:{series_id}"))
        elif record.revision_policy == EdgeSeriesRevisionPolicy.UNKNOWN.value:
            needs_external.append(_reason(f"series_revision_policy_unknown:{series_id}"))
    if not coverage:
        fail.append(_reason("instrument_coverage_empty"))
    return fail, needs_external


# --- EF-3 manifest --------------------------------------------------------------------------------------------------


def _assemble_source_packet_evidence(
    *,
    root_intake_binding: object,
    data_requirement_registry_binding: object,
    manifest_id: object,
    correlation_id: object,
    input_series: object,
) -> EdgeSourcePacketEvidence:
    """The one EF-3 assembly path, shared by the builder and verifier reassembly."""

    root_binding = require_edge_authority_binding(
        root_intake_binding,
        shape=edge_idea_intake_evidence_payload_is_well_formed,
        error=EdgeSourcePacketEvidenceError,
        code=_reason("root_intake"),
        optional=False,
    )
    registry_binding = require_edge_authority_binding(
        data_requirement_registry_binding,
        shape=_registry_snapshot_is_well_formed,
        error=EdgeSourcePacketEvidenceError,
        code=_reason("data_requirement_registry"),
        optional=False,
    )
    manifest_id = _require_text(manifest_id, "manifest_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    series = _canonical_input_series(input_series)

    root_codes, root = _root_intake_authority(root_binding, correlation_id)  # type: ignore[arg-type]
    registry_codes, registry = _registry_authority(registry_binding)  # type: ignore[arg-type]
    integrity = _sorted_unique([*root_codes, *registry_codes])
    records = tuple(_series_record(item, registry) for item in series)
    coverage = _instrument_coverage(series)

    if integrity or root is None:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        fail, needs_external = _verdict_reasons(root, records, coverage)
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, ())
        verdict_reasons = _sorted_unique(fail + needs_external)

    seed = EdgeSourcePacketEvidence(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        manifest_id=manifest_id,
        correlation_id=correlation_id,
        root_intake_binding=root_binding,  # type: ignore[arg-type]
        root_intake_digest=root_binding.expected_digest,  # type: ignore[union-attr]
        predecessor_gate_id=_PREDECESSOR_GATE_ID,
        predecessor_digest=root_binding.expected_digest,  # type: ignore[union-attr]
        candidate_strategy_id="" if root is None else root.candidate_strategy_id,
        edge_family="" if root is None else root.edge_family,
        intake_data_requirement_keys=() if root is None else root.data_requirement_keys,
        data_requirement_registry_binding=registry_binding,  # type: ignore[arg-type]
        data_requirement_registry_digest=registry_binding.expected_digest,  # type: ignore[union-attr]
        data_requirement_registry_schema_version="" if registry is None else registry.schema_version,
        series=records,
        instrument_coverage=coverage,
        feature_input_series_ids=tuple(record.series_id for record in records if record.feature_input_eligible),
        regime_label_binding_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        regime_evidence_status=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        source_packet_evidence_digest="",
    )
    return replace(seed, source_packet_evidence_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_edge_source_packet_evidence(
    root_intake: EdgeIdeaIntakeEvidence,
    *,
    expected_root_intake_digest: str,
    data_requirement_registry: DataRequirementRegistry,
    expected_data_requirement_registry_digest: str,
    manifest_id: str,
    correlation_id: str,
    input_series: Sequence[EdgeInputSeries],
) -> EdgeSourcePacketEvidence:
    """Build a deterministic EF-3 point-in-time data manifest over an EF-2 root and the data requirement registry.

    Malformed caller input or a non-serializable upstream object raises ``EdgeSourcePacketEvidenceError``. An
    authentic root or registry that fails re-proof (or a correlation splice) yields ``REJECTED``/``NOT_EVALUATED``.
    Otherwise the manifest is ``READY`` with ``FAIL``, ``NEEDS_EXTERNAL_FACTS`` (unknown finality or revision policy)
    or ``PASS``.
    """

    if type(root_intake) is not EdgeIdeaIntakeEvidence:
        raise _fail("root_intake_malformed")
    try:
        root_payload = edge_idea_intake_evidence_to_dict(root_intake)
    except Exception as exc:  # noqa: BLE001 - a hollow root object is a construction error, never a receipt
        raise _fail("root_intake_not_serializable") from exc
    root_binding = build_edge_authority_binding(
        snapshot_payload=root_payload,
        expected_digest=expected_root_intake_digest,
        shape=edge_idea_intake_evidence_payload_is_well_formed,
        error=EdgeSourcePacketEvidenceError,
        code=_reason("root_intake"),
    )
    if type(data_requirement_registry) is not DataRequirementRegistry:
        raise _fail("data_requirement_registry_malformed")
    try:
        registry_payload = data_requirement_registry_to_dict(data_requirement_registry)
    except Exception as exc:  # noqa: BLE001 - a hollow registry object is a construction error, never a receipt
        raise _fail("data_requirement_registry_not_serializable") from exc
    registry_binding = build_edge_authority_binding(
        snapshot_payload=registry_payload,
        expected_digest=expected_data_requirement_registry_digest,
        shape=_registry_snapshot_is_well_formed,
        error=EdgeSourcePacketEvidenceError,
        code=_reason("data_requirement_registry"),
    )
    return _assemble_source_packet_evidence(
        root_intake_binding=root_binding,
        data_requirement_registry_binding=registry_binding,
        manifest_id=manifest_id,
        correlation_id=correlation_id,
        input_series=input_series,
    )


def edge_source_packet_evidence_to_dict(evidence: EdgeSourcePacketEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-3 evidence, including its self-digest."""

    return _to_payload(evidence)


def edge_source_packet_evidence_digest(evidence: EdgeSourcePacketEvidence) -> str:
    """Recompute the canonical EF-3 digest, excluding only the self-digest field."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


def _parse_root_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_idea_intake_evidence_payload_is_well_formed,
        error=EdgeSourcePacketEvidenceError,
        code=_reason("root_intake"),
        optional=False,
    )


def _parse_registry_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=_registry_snapshot_is_well_formed,
        error=EdgeSourcePacketEvidenceError,
        code=_reason("data_requirement_registry"),
        optional=False,
    )


_RECORD_CONVERTERS: dict[str, Callable[[object], object]] = {
    "instrument_coverage": _as_str_tuple,
    "registry_requirement_bound": _as_bool,
    **dict.fromkeys(_REQUIREMENT_FIELDS - {"key", "order_book_depth"}, _as_optional_str),
    "order_book_depth": _as_optional_int,
    "paper_parity_available": _as_bool,
    "rights_usable": _as_bool,
    "finalized_only": _as_bool,
    "point_in_time_revision_safe": _as_bool,
    "feature_input_eligible": _as_bool,
}


def _as_records(value: object) -> tuple[EdgeSourceSeriesRecord, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_parse_exact(EdgeSourceSeriesRecord, entry, _RECORD_CONVERTERS) for entry in value)  # type: ignore[misc]


_EVIDENCE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "root_intake_binding": _parse_root_binding,
    "intake_data_requirement_keys": _as_str_tuple,
    "data_requirement_registry_binding": _parse_registry_binding,
    "series": _as_records,
    "instrument_coverage": _as_str_tuple,
    "feature_input_series_ids": _as_str_tuple,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def edge_source_packet_evidence_from_payload(payload: object) -> EdgeSourcePacketEvidence:
    """Strictly reconstruct EF-3 evidence from its serialized payload (exact fields, types and bindings).

    Reconstruction is not verification: consumers call ``verify_edge_source_packet_evidence`` on the result.
    """

    return _parse_exact(EdgeSourcePacketEvidence, payload, _EVIDENCE_CONVERTERS)  # type: ignore[return-value]


def edge_source_packet_evidence_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an EF-3 predecessor snapshot."""

    try:
        edge_source_packet_evidence_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_source_packet_evidence(evidence: object) -> EdgeSourcePacketEvidence:
    return _assemble_source_packet_evidence(
        root_intake_binding=evidence.root_intake_binding,  # type: ignore[attr-defined]
        data_requirement_registry_binding=evidence.data_requirement_registry_binding,  # type: ignore[attr-defined]
        manifest_id=evidence.manifest_id,  # type: ignore[attr-defined]
        correlation_id=evidence.correlation_id,  # type: ignore[attr-defined]
        input_series=tuple(
            EdgeInputSeries(
                series_id=record.series_id,
                data_requirement_key=record.data_requirement_key,
                source_reference=record.source_reference,
                rights_status=record.rights_status,
                rights_reference=record.rights_reference,
                finality=record.finality,
                revision_policy=record.revision_policy,
                instrument_coverage=record.instrument_coverage,
            )
            for record in evidence.series  # type: ignore[attr-defined]
        ),
    )


def verify_edge_source_packet_evidence(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove EF-3 evidence by strict parse and reassembly from its carried bindings and declarations.

    READY and builder-produced REJECTED artifacts alike must equal the reassembled artifact. Total: never raises.
    """

    return verify_edge_artifact_total(
        evidence,
        cls=EdgeSourcePacketEvidence,
        to_payload=_to_payload,
        parse_payload=edge_source_packet_evidence_from_payload,
        reassemble=_reassemble_source_packet_evidence,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
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
    "edge_source_packet_evidence_from_payload",
    "edge_source_packet_evidence_payload_is_well_formed",
    "edge_source_packet_evidence_to_dict",
    "verify_edge_source_packet_evidence",
]
