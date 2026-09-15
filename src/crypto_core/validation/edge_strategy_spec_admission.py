"""Edge Factory EF-4: deterministic edge StrategySpec admission, closing the candidate admission spine.

EF-4 is the third gate of ``docs/crypto_core/edge_factory_design.md``. It binds an independently validated
``crypto_core.strategy.spec.StrategySpec`` to the EF-2 intake (root anchor) and the EF-3 PIT data manifest (immediate
predecessor).

Contract:

* Dual anchor. The EF-2 root and the EF-3 predecessor are each re-proven through their public verifiers and matched to
  caller anchors, and both must be READY + PASS (a FAIL or NEEDS_* gate never advances). The EF-3 packet must carry
  the same verified root digest and the same declared data requirements as the supplied root, and every artifact the
  same correlation id, so a packet from another chain cannot be spliced in.
* StrategySpec authority stays in ``strategy/spec.py``: one canonical snapshot through its public serializer (NaN and
  Infinity never parse), its digest matched to the caller anchor, full ``validate_strategy_spec`` acceptance, and the
  validated spec re-serialized to the same digest, so a forged or non-canonical spec is REJECTED. Spec text is also
  scanned for BIST and live/private/order/scheduler tokens, which the spec validator checks only in keys.
* Semantic admission (READY + FAIL when violated): ``strategy_id`` equals the intake candidate strategy id and
  ``edge_family`` the intake edge family; every ``instrument_universe`` member is inside the EF-3 packet coverage;
  every spec data-requirement key, normalized as ``validation/pit_parity.py`` normalizes it, is an EF-3 series key.
* Kill criteria may only strengthen. Every EF-2 draft criterion must be present and identical: a removal, or a changed
  (relaxed or tightened) threshold, comparator, metric or basis FAILs. New criteria may be added; under the
  "any single criterion kills" combination an addition can only make the kill set stricter. The spec's
  ``kill_switch_triggers`` must be exactly the admitted criterion ids. Thresholds stay governance-owned: a pending
  threshold or a missing approval is ``NEEDS_GOVERNANCE_APPROVAL``. Criteria are not sealed here (EF-7 seals).
* Fee, funding, slippage and latency requirements are recorded verbatim from the spec; no current venue fact is
  consumed or substituted.
* Regime: the spec's ``expected_regime`` is recorded verbatim with the EF-2 digest-bound pending pattern. The RF chain
  does not exist, so no regime label is bound and regime evidence stays unavailable.
* ``status`` (integrity) and ``gate_verdict`` (outcome) stay separate exactly as in EF-2; only READY + PASS advances.
  Paper-only, deterministic, immutable, and every structural non-claim of EF-2: admission of a specification into the
  process is never an edge, profitability, readiness, live, order or capital claim.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum

from crypto_core.data.requirements import DataRequirementKey
from crypto_core.strategy.spec import (
    StrategySpec,
    canonical_strategy_spec_json,
    strategy_spec_digest,
    validate_strategy_spec,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    EdgeIdeaIntakeEvidence,
    EdgeIdeaIntakeEvidenceError,
    EdgeKillCriterion,
    canonical_edge_kill_criteria,
    edge_kill_criteria_digest,
    edge_kill_criteria_from_payload,
    edge_kill_criterion_to_dict,
    resolve_edge_gate_verdict,
    verify_edge_idea_intake_evidence,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourcePacketEvidence,
    verify_edge_source_packet_evidence,
)

_SCHEMA_VERSION = "edge-strategy-spec-admission.v1"
_GATE_ID = "EF-4"
_ROOT_GATE_ID = "EF-2"
_PREDECESSOR_GATE_ID = "EF-3"
_REASON_PREFIX = "edge_strategy_spec_admission"
_SELF_DIGEST_FIELD = "admission_digest"
_KILL_CRITERIA_LIFECYCLE_STAGE = "SPEC_BOUND_STRENGTHEN_ONLY"
_KILL_CRITERIA_LIFECYCLE_POLICY = "draft_criteria_preserved_exactly_additions_only.v1"
_SPEC_DATA_REQUIREMENT_KEY_NORMALIZATION = "strip_lower_as_validation_pit_parity.v1"
_COST_MODEL_BINDING = "strategy_spec_requirements_recorded_verbatim_no_venue_fact_values.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_DATA_REQUIREMENT_KEY_VALUES = frozenset(key.value for key in DataRequirementKey)
# Same scope vocabulary as EF-2 (see edge_idea_intake_evidence.py).
_BIST_PATTERN = re.compile(r"(?<![a-z0-9])(?:bist|borsa|matriks)|(?<![a-z0-9])kap(?![a-z0-9])", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:private_api|private_key|api_key|api_secret|credential|order_router|place_order|live_order"
    r"|real_order|order_id|auto_loop|shadow_live_execution|scheduler)"
    r"|(?<![a-z0-9])live(?![a-z0-9])",
    re.IGNORECASE,
)


class EdgeStrategySpecAdmissionError(RuntimeError):
    """Raised on malformed caller input or a forbidden BIST/live/private/order/scheduler token."""


@dataclass(frozen=True)
class EdgeStrategySpecAdmission:
    """Immutable, digest-bound EF-4 StrategySpec admission. PAPER ONLY; proves process survival, never an edge."""

    schema_version: str
    gate_id: str
    root_gate_id: str
    predecessor_gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    admission_id: str
    correlation_id: str
    expected_root_intake_digest: str
    verified_root_intake_digest: str
    expected_source_packet_evidence_digest: str
    verified_source_packet_evidence_digest: str
    expected_strategy_spec_digest: str
    verified_strategy_spec_digest: str
    intake_candidate_strategy_id: str
    intake_edge_family: str
    packet_instrument_coverage: tuple[str, ...]
    packet_series_keys: tuple[str, ...]
    strategy_id: str
    strategy_version: str
    strategy_family: str
    edge_family: str
    market_type: str
    instrument_universe: tuple[str, ...]
    spec_data_requirement_keys: tuple[str, ...]
    spec_data_requirement_key_normalization: str
    spec_kill_switch_triggers: tuple[str, ...]
    fee_model_requirement: str
    funding_sensitivity: str
    slippage_model_requirement: str
    latency_sensitivity: str
    cost_model_binding: str
    expected_regime_declared: str
    regime_label_binding_status: str
    regime_evidence_status: str
    draft_kill_criteria: tuple[EdgeKillCriterion, ...]
    draft_kill_criteria_digest: str
    kill_criteria: tuple[EdgeKillCriterion, ...]
    kill_criteria_digest: str
    kill_criteria_added_ids: tuple[str, ...]
    kill_criteria_lifecycle_stage: str
    kill_criteria_lifecycle_policy: str
    kill_criteria_thresholds_approved: bool
    kill_criteria_approval_reference: str | None
    kill_criteria_approval_digest: str | None
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    admission_digest: str
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
    ("root_gate_id", _ROOT_GATE_ID),
    ("predecessor_gate_id", _PREDECESSOR_GATE_ID),
    ("spec_data_requirement_key_normalization", _SPEC_DATA_REQUIREMENT_KEY_NORMALIZATION),
    ("cost_model_binding", _COST_MODEL_BINDING),
    ("regime_label_binding_status", EDGE_REGIME_LABEL_BINDING_PENDING),
    ("regime_evidence_status", EDGE_REGIME_EVIDENCE_UNAVAILABLE),
    ("kill_criteria_lifecycle_stage", _KILL_CRITERIA_LIFECYCLE_STAGE),
    ("kill_criteria_lifecycle_policy", _KILL_CRITERIA_LIFECYCLE_POLICY),
)
_DIGEST_PAIRS = (
    ("expected_root_intake_digest", "verified_root_intake_digest"),
    ("expected_source_packet_evidence_digest", "verified_source_packet_evidence_digest"),
    ("expected_strategy_spec_digest", "verified_strategy_spec_digest"),
)
_TEXT_FIELDS = (
    "admission_id",
    "correlation_id",
    "intake_candidate_strategy_id",
    "intake_edge_family",
    "strategy_id",
    "strategy_version",
    "strategy_family",
    "edge_family",
    "market_type",
    "fee_model_requirement",
    "funding_sensitivity",
    "slippage_model_requirement",
    "latency_sensitivity",
    "expected_regime_declared",
)


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
    # Verification-side check. Recorded text is partly StrategySpec-owned (stripped, non-empty, scope-scanned at build
    # time but free to contain inner whitespace), so presence plus the build-time scope scan is re-checked here.
    return type(value) is str and value != "" and _scope_violation(value) is None


def _require_text(value: object, field_name: str) -> str:
    if not _is_plain_text(value):
        raise EdgeStrategySpecAdmissionError(_reason(f"{field_name}_invalid"))
    violation = _scope_violation(value)  # type: ignore[arg-type]
    if violation is not None:
        raise EdgeStrategySpecAdmissionError(_reason(f"{violation}:{field_name}"))
    return value  # type: ignore[return-value]


def _is_canonical_reason_list(value: object) -> bool:
    return (
        type(value) is list
        and all(type(code) is str and code.startswith(f"{_REASON_PREFIX}:") for code in value)
        and value == sorted(set(value))
    )


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant {value}")


def _collect_strings(value: object) -> list[str]:
    """Every string of a JSON snapshot (dict keys, values and list items), for the scope scan."""

    out: list[str] = []
    if type(value) is str:
        out.append(value)
    elif type(value) is list:
        for item in value:
            out.extend(_collect_strings(item))
    elif type(value) is dict:
        for key, item in value.items():
            out.append(key)
            out.extend(_collect_strings(item))
    return out


def _consume_gate(
    verification: EdgeEvidenceVerification, expected_digest: str, correlation_id: str, role: str
) -> tuple[list[str], dict[str, object] | None]:
    if not verification.intact:
        return [_reason(f"{role}_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != expected_digest:
        return [_reason(f"{role}_digest_mismatch")], None
    snapshot = json.loads(verification.canonical_json)
    failures: list[str] = []
    if (
        snapshot["status"] != EdgeEvidenceStatus.READY.value
        or snapshot["gate_verdict"] != EdgeGateVerdict.PASS.value
        or snapshot["advances"] is not True
    ):
        failures.append(_reason(f"{role}_not_passed:{snapshot['gate_verdict']}"))
    if snapshot["correlation_id"] != correlation_id:
        failures.append(_reason(f"{role}_correlation_id_mismatch"))
    return failures, snapshot


def _strategy_spec_proof(spec: StrategySpec, expected_digest: str) -> tuple[list[str], dict[str, object] | None]:
    """Re-prove a StrategySpec from ONE canonical snapshot: anchor, public validation, canonical re-serialization."""

    try:
        canonical = canonical_strategy_spec_json(spec)
        snapshot = json.loads(canonical, parse_constant=_reject_json_constant)
    except Exception:  # noqa: BLE001 - a forged or non-serializable spec must fail closed, never crash
        return [_reason("strategy_spec_malformed_payload")], None
    if type(snapshot) is not dict:
        return [_reason("strategy_spec_malformed_payload")], None
    failures: list[str] = []
    recomputed = _sha256(canonical)
    if recomputed != expected_digest:
        failures.append(_reason("strategy_spec_digest_mismatch"))
    try:
        validation = validate_strategy_spec(snapshot)
    except Exception:  # noqa: BLE001 - validation over a forged snapshot must fail closed
        validation = None
    if validation is None or validation.accepted is not True or type(validation.spec) is not StrategySpec:
        failures.append(_reason("strategy_spec_invalid"))
    elif strategy_spec_digest(validation.spec) != recomputed:
        failures.append(_reason("strategy_spec_noncanonical"))
    if any(_scope_violation(text) is not None for text in _collect_strings(snapshot)):
        failures.append(_reason("strategy_spec_scope_violation"))
    return failures, snapshot


def _snapshot_text(snapshot: Mapping[str, object] | None, key: str) -> str:
    value = None if snapshot is None else snapshot.get(key)
    return value if type(value) is str else ""


def _snapshot_texts(snapshot: Mapping[str, object] | None, key: str) -> tuple[str, ...]:
    value = None if snapshot is None else snapshot.get(key)
    if type(value) is not list or any(type(item) is not str for item in value):
        return ()
    return tuple(value)


def _packet_series_keys(snapshot: Mapping[str, object] | None) -> tuple[str, ...]:
    series = None if snapshot is None else snapshot.get("series")
    if type(series) is not list or any(
        type(record) is not dict or type(record.get("data_requirement_key")) is not str for record in series
    ):
        return ()
    return tuple(sorted(record["data_requirement_key"] for record in series))


def _spec_data_requirement_keys(snapshot: Mapping[str, object] | None) -> tuple[str, ...]:
    requirements = None if snapshot is None else snapshot.get("data_requirements")
    if type(requirements) is not dict:
        return ()
    return tuple(sorted({key.strip().lower() for key in requirements}))


def _admission_verdict_reasons(
    *,
    intake_candidate_strategy_id: object,
    intake_edge_family: object,
    strategy_id: object,
    edge_family: object,
    instrument_universe: Sequence[str],
    packet_instrument_coverage: Sequence[str],
    spec_data_requirement_keys: Sequence[str],
    packet_series_keys: Sequence[str],
    spec_kill_switch_triggers: Sequence[str],
    draft_kill_criteria: Sequence[EdgeKillCriterion],
    kill_criteria: Sequence[EdgeKillCriterion],
    thresholds_approved: object,
    approval_reference: object,
    approval_digest: object,
) -> tuple[list[str], list[str], list[str]]:
    fail: list[str] = []
    if strategy_id != intake_candidate_strategy_id:
        fail.append(_reason("candidate_strategy_id_mismatch"))
    if edge_family != intake_edge_family:
        fail.append(_reason("edge_family_mismatch"))
    fail.extend(
        _reason(f"instrument_outside_packet_coverage:{symbol}")
        for symbol in sorted(set(instrument_universe))
        if symbol not in packet_instrument_coverage
    )
    fail.extend(
        _reason(f"spec_data_requirement_not_in_packet:{key}")
        for key in spec_data_requirement_keys
        if key not in packet_series_keys
    )
    admitted = {criterion.criterion_id: criterion for criterion in kill_criteria}
    if set(spec_kill_switch_triggers) != set(admitted):
        fail.append(_reason("spec_kill_switch_triggers_not_bound_to_kill_criteria"))
    for draft in draft_kill_criteria:
        current = admitted.get(draft.criterion_id)
        if current is None:
            fail.append(_reason(f"kill_criterion_removed:{draft.criterion_id}"))
        elif current != draft:
            fail.append(_reason(f"kill_criterion_modified:{draft.criterion_id}"))
    needs_governance = [
        _reason(f"kill_criterion_threshold_pending_governance:{criterion.criterion_id}")
        for criterion in kill_criteria
        if criterion.threshold is None
    ]
    if thresholds_approved is not True:
        needs_governance.append(_reason("kill_criteria_thresholds_not_approved"))
    elif not _is_plain_text(approval_reference) or not _is_hex64(approval_digest):
        needs_governance.append(_reason("kill_criteria_approval_incomplete"))
    return fail, [], needs_governance


def build_edge_strategy_spec_admission(
    intake: EdgeIdeaIntakeEvidence,
    source_packet_evidence: EdgeSourcePacketEvidence,
    strategy_spec: StrategySpec,
    *,
    expected_root_intake_digest: str,
    expected_source_packet_evidence_digest: str,
    expected_strategy_spec_digest: str,
    kill_criteria: Sequence[EdgeKillCriterion],
    admission_id: str,
    correlation_id: str,
    kill_criteria_thresholds_approved: bool = False,
    kill_criteria_approval_reference: str | None = None,
    kill_criteria_approval_digest: str | None = None,
) -> EdgeStrategySpecAdmission:
    """Build deterministic EF-4 admission of a validated StrategySpec against a re-proven EF-2 root and EF-3 packet.

    Malformed caller input raises ``EdgeStrategySpecAdmissionError``. A root, packet or spec that fails re-proof, a
    root or packet that is not READY + PASS, or a spliced chain yields ``REJECTED`` / ``NOT_EVALUATED``. Otherwise the
    admission is ``READY`` with a ``FAIL``, ``NEEDS_GOVERNANCE_APPROVAL`` or ``PASS`` verdict.
    """

    if type(intake) is not EdgeIdeaIntakeEvidence:
        raise EdgeStrategySpecAdmissionError(_reason("root_intake_malformed"))
    if type(source_packet_evidence) is not EdgeSourcePacketEvidence:
        raise EdgeStrategySpecAdmissionError(_reason("source_packet_evidence_malformed"))
    if type(strategy_spec) is not StrategySpec:
        raise EdgeStrategySpecAdmissionError(_reason("strategy_spec_malformed"))
    for name, value in (
        ("expected_root_intake_digest", expected_root_intake_digest),
        ("expected_source_packet_evidence_digest", expected_source_packet_evidence_digest),
        ("expected_strategy_spec_digest", expected_strategy_spec_digest),
    ):
        if not _is_hex64(value):
            raise EdgeStrategySpecAdmissionError(_reason(f"{name}_invalid"))
    admission_id = _require_text(admission_id, "admission_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    try:
        admitted = canonical_edge_kill_criteria(kill_criteria)
    except EdgeIdeaIntakeEvidenceError as exc:
        raise EdgeStrategySpecAdmissionError(_reason(f"kill_criteria_invalid:{exc}")) from exc
    if type(kill_criteria_thresholds_approved) is not bool:
        raise EdgeStrategySpecAdmissionError(_reason("kill_criteria_thresholds_approved_invalid"))
    if kill_criteria_approval_reference is not None:
        kill_criteria_approval_reference = _require_text(
            kill_criteria_approval_reference, "kill_criteria_approval_reference"
        )
    if kill_criteria_approval_digest is not None and not _is_hex64(kill_criteria_approval_digest):
        raise EdgeStrategySpecAdmissionError(_reason("kill_criteria_approval_digest_invalid"))

    root_failures, intake_snapshot = _consume_gate(
        verify_edge_idea_intake_evidence(intake), expected_root_intake_digest, correlation_id, "root_intake"
    )
    packet_failures, packet_snapshot = _consume_gate(
        verify_edge_source_packet_evidence(source_packet_evidence),
        expected_source_packet_evidence_digest,
        correlation_id,
        "predecessor_source_packet",
    )
    chain_failures: list[str] = []
    if (
        intake_snapshot is not None
        and packet_snapshot is not None
        and packet_snapshot["status"] == EdgeEvidenceStatus.READY.value
    ):
        if packet_snapshot["verified_root_intake_digest"] != expected_root_intake_digest:
            chain_failures.append(_reason("chain_splice_root_intake_mismatch"))
        if packet_snapshot["declared_data_requirement_keys"] != intake_snapshot["data_requirement_keys"]:
            chain_failures.append(_reason("chain_splice_declared_data_requirements_mismatch"))
    spec_failures, spec_snapshot = _strategy_spec_proof(strategy_spec, expected_strategy_spec_digest)
    integrity = _sorted_unique(root_failures + packet_failures + chain_failures + spec_failures)

    try:
        draft = (
            () if intake_snapshot is None else edge_kill_criteria_from_payload(intake_snapshot["kill_criteria_draft"])
        )
    except Exception:  # noqa: BLE001 - a non-canonical carried draft of a non-passing root is only recorded as absent
        draft = ()
    packet_coverage = _snapshot_texts(packet_snapshot, "packet_instrument_coverage")
    packet_series_keys = _packet_series_keys(packet_snapshot)
    instrument_universe = _snapshot_texts(spec_snapshot, "instrument_universe")
    spec_keys = _spec_data_requirement_keys(spec_snapshot)
    spec_triggers = _snapshot_texts(spec_snapshot, "kill_switch_triggers")
    intake_candidate_strategy_id = _snapshot_text(intake_snapshot, "candidate_strategy_id")
    intake_edge_family = _snapshot_text(intake_snapshot, "edge_family")
    strategy_id = _snapshot_text(spec_snapshot, "strategy_id")
    edge_family = _snapshot_text(spec_snapshot, "edge_family")

    if integrity:
        status = EdgeEvidenceStatus.REJECTED
        verdict = EdgeGateVerdict.NOT_EVALUATED
        verdict_reasons: tuple[str, ...] = ()
        verified_root = verified_packet = verified_spec = ""
    else:
        fail, needs_external, needs_governance = _admission_verdict_reasons(
            intake_candidate_strategy_id=intake_candidate_strategy_id,
            intake_edge_family=intake_edge_family,
            strategy_id=strategy_id,
            edge_family=edge_family,
            instrument_universe=instrument_universe,
            packet_instrument_coverage=packet_coverage,
            spec_data_requirement_keys=spec_keys,
            packet_series_keys=packet_series_keys,
            spec_kill_switch_triggers=spec_triggers,
            draft_kill_criteria=draft,
            kill_criteria=admitted,
            thresholds_approved=kill_criteria_thresholds_approved,
            approval_reference=kill_criteria_approval_reference,
            approval_digest=kill_criteria_approval_digest,
        )
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)
        verified_root = expected_root_intake_digest
        verified_packet = expected_source_packet_evidence_digest
        verified_spec = expected_strategy_spec_digest

    seed = EdgeStrategySpecAdmission(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        root_gate_id=_ROOT_GATE_ID,
        predecessor_gate_id=_PREDECESSOR_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        admission_id=admission_id,
        correlation_id=correlation_id,
        expected_root_intake_digest=expected_root_intake_digest,
        verified_root_intake_digest=verified_root,
        expected_source_packet_evidence_digest=expected_source_packet_evidence_digest,
        verified_source_packet_evidence_digest=verified_packet,
        expected_strategy_spec_digest=expected_strategy_spec_digest,
        verified_strategy_spec_digest=verified_spec,
        intake_candidate_strategy_id=intake_candidate_strategy_id,
        intake_edge_family=intake_edge_family,
        packet_instrument_coverage=packet_coverage,
        packet_series_keys=packet_series_keys,
        strategy_id=strategy_id,
        strategy_version=_snapshot_text(spec_snapshot, "strategy_version"),
        strategy_family=_snapshot_text(spec_snapshot, "strategy_family"),
        edge_family=edge_family,
        market_type=_snapshot_text(spec_snapshot, "market_type"),
        instrument_universe=instrument_universe,
        spec_data_requirement_keys=spec_keys,
        spec_data_requirement_key_normalization=_SPEC_DATA_REQUIREMENT_KEY_NORMALIZATION,
        spec_kill_switch_triggers=spec_triggers,
        fee_model_requirement=_snapshot_text(spec_snapshot, "fee_model_requirement"),
        funding_sensitivity=_snapshot_text(spec_snapshot, "funding_sensitivity"),
        slippage_model_requirement=_snapshot_text(spec_snapshot, "slippage_model_requirement"),
        latency_sensitivity=_snapshot_text(spec_snapshot, "latency_sensitivity"),
        cost_model_binding=_COST_MODEL_BINDING,
        expected_regime_declared=_snapshot_text(spec_snapshot, "expected_regime"),
        regime_label_binding_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        regime_evidence_status=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        draft_kill_criteria=draft,
        draft_kill_criteria_digest=edge_kill_criteria_digest(draft) if draft else "",
        kill_criteria=admitted,
        kill_criteria_digest=edge_kill_criteria_digest(admitted),
        kill_criteria_added_ids=_added_ids(draft, admitted),
        kill_criteria_lifecycle_stage=_KILL_CRITERIA_LIFECYCLE_STAGE,
        kill_criteria_lifecycle_policy=_KILL_CRITERIA_LIFECYCLE_POLICY,
        kill_criteria_thresholds_approved=kill_criteria_thresholds_approved,
        kill_criteria_approval_reference=kill_criteria_approval_reference,
        kill_criteria_approval_digest=kill_criteria_approval_digest,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        admission_digest="",
    )
    return replace(seed, admission_digest=edge_strategy_spec_admission_digest(seed))


def _added_ids(draft: Sequence[EdgeKillCriterion], admitted: Sequence[EdgeKillCriterion]) -> tuple[str, ...]:
    draft_ids = {criterion.criterion_id for criterion in draft}
    return tuple(sorted(criterion.criterion_id for criterion in admitted if criterion.criterion_id not in draft_ids))


def _serialize(value: object) -> object:
    if type(value) is EdgeKillCriterion:
        return edge_kill_criterion_to_dict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def edge_strategy_spec_admission_to_dict(admission: EdgeStrategySpecAdmission) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-4 admission evidence, including its self-digest."""

    return {field.name: _serialize(getattr(admission, field.name)) for field in fields(admission)}


def edge_strategy_spec_admission_digest(admission: EdgeStrategySpecAdmission) -> str:
    """Recompute the canonical admission digest, excluding only the self-digest field."""

    payload = edge_strategy_spec_admission_to_dict(admission)
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


def _is_sorted_unique_list(value: object) -> bool:
    return type(value) is list and bool(value) and value == sorted(set(value))


def _admission_semantic_failures(body: Mapping[str, object]) -> list[str]:
    failures: list[str] = []
    for name in _TEXT_FIELDS:
        if not _is_clean_text(body.get(name)):
            failures.append(_reason(f"text_field_invalid:{name}"))
    for expected_name, verified_name in _DIGEST_PAIRS:
        if not _is_hex64(body.get(expected_name)) or body.get(verified_name) != body.get(expected_name):
            failures.append(_reason(f"verified_digest_mismatch:{verified_name}"))
    coverage = body.get("packet_instrument_coverage")
    series_keys = body.get("packet_series_keys")
    universe = body.get("instrument_universe")
    spec_keys = body.get("spec_data_requirement_keys")
    triggers = body.get("spec_kill_switch_triggers")
    if (
        not _is_sorted_unique_list(coverage)
        or any(not _is_clean_text(symbol) for symbol in coverage)  # type: ignore[union-attr]
        or not _is_sorted_unique_list(series_keys)
        or not set(series_keys) <= _DATA_REQUIREMENT_KEY_VALUES  # type: ignore[arg-type]
        or type(universe) is not list
        or not universe
        or any(not _is_clean_text(symbol) for symbol in universe)
        or not _is_sorted_unique_list(spec_keys)
        or any(type(key) is not str for key in spec_keys)  # type: ignore[union-attr]
        or type(triggers) is not list
        or not triggers
        or any(not _is_clean_text(trigger) for trigger in triggers)
    ):
        failures.append(_reason("bound_collections_noncanonical"))
        return failures
    draft = edge_kill_criteria_from_payload(body.get("draft_kill_criteria"))
    admitted = edge_kill_criteria_from_payload(body.get("kill_criteria"))
    if (
        edge_kill_criteria_digest(draft) != body.get("draft_kill_criteria_digest")
        or edge_kill_criteria_digest(admitted) != body.get("kill_criteria_digest")
        or list(_added_ids(draft, admitted)) != body.get("kill_criteria_added_ids")
    ):
        failures.append(_reason("kill_criteria_binding_mismatch"))
    approved = body.get("kill_criteria_thresholds_approved")
    reference = body.get("kill_criteria_approval_reference")
    approval_digest = body.get("kill_criteria_approval_digest")
    if (
        type(approved) is not bool
        or (reference is not None and not _is_clean_text(reference))
        or (approval_digest is not None and not _is_hex64(approval_digest))
    ):
        failures.append(_reason("kill_criteria_approval_malformed"))
    fail, needs_external, needs_governance = _admission_verdict_reasons(
        intake_candidate_strategy_id=body.get("intake_candidate_strategy_id"),
        intake_edge_family=body.get("intake_edge_family"),
        strategy_id=body.get("strategy_id"),
        edge_family=body.get("edge_family"),
        instrument_universe=universe,
        packet_instrument_coverage=coverage,  # type: ignore[arg-type]
        spec_data_requirement_keys=spec_keys,  # type: ignore[arg-type]
        packet_series_keys=series_keys,  # type: ignore[arg-type]
        spec_kill_switch_triggers=triggers,
        draft_kill_criteria=draft,
        kill_criteria=admitted,
        thresholds_approved=approved,
        approval_reference=reference,
        approval_digest=approval_digest,
    )
    rederived = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
    if list(_sorted_unique(fail + needs_external + needs_governance)) != body.get(
        "verdict_reason_codes"
    ) or rederived.value != body.get("gate_verdict"):
        failures.append(_reason("verdict_rederivation_mismatch"))
    return failures


def verify_edge_strategy_spec_admission(admission: object) -> EdgeEvidenceVerification:
    """Re-prove EF-4 admission evidence: exact type, self-digest, constants, non-claims, status/verdict coherence, and
    (when READY) the kill-criteria lifecycle and verdict re-derived from the carried fields. Never raises."""

    if (
        type(admission) is not EdgeStrategySpecAdmission
        or type(admission.status) is not EdgeEvidenceStatus
        or type(admission.gate_verdict) is not EdgeGateVerdict
    ):
        return EdgeEvidenceVerification(False, (_reason("evidence_type_invalid"),), "", "")
    try:
        canonical = _canonical_json(edge_strategy_spec_admission_to_dict(admission))
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
            failures.extend(_admission_semantic_failures(body))
        except Exception:  # noqa: BLE001 - malformed carried semantics fail closed
            failures.append(_reason("evidence_semantics_malformed"))
    codes = _sorted_unique(failures)
    return EdgeEvidenceVerification(
        intact=not codes, reason_codes=codes, recomputed_digest=recomputed, canonical_json=canonical
    )


__all__ = [
    "EdgeStrategySpecAdmission",
    "EdgeStrategySpecAdmissionError",
    "build_edge_strategy_spec_admission",
    "edge_strategy_spec_admission_digest",
    "edge_strategy_spec_admission_to_dict",
    "verify_edge_strategy_spec_admission",
]
