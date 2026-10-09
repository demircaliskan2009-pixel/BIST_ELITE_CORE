"""RF-6 regime filter admission decision (RF6_REGIME_FILTER_ADMISSION_DECISION_V1).

Design authority: ``docs/crypto_core/regime_volatility_filter_design.md`` section 1 (RF-6) and section 8, closure
``EF5_RF6_REGIME_POLICY_PREREGISTRATION_ADMISSION_V1``.

RF-6 decides whether ONE exact RF-2 regime filter policy is admitted for the ONE exact strategy spec an EF-5
preregistration seals. It consumes:
* the RF-2 policy, re-proven through ``verify_regime_feature_policy``;
* the EF-5 preregistration, bound as an exact snapshot with the caller's digest anchor, parsed back from that snapshot
  and re-proven through ``verify_edge_leakage_bias_evidence``. It must equal the anchor, carry the caller's root intake
  anchor and be ``READY``; a defect raises;
* the RF-5 stability evidence, rebuilt from its exact inputs through the accepted builder (which rebuilds both RF-4 label
  evidences and both RF-3 feature series), canonically equal, and pinned to exactly the supplied policy.

Identity binding on this entry path, each defect raising ``RegimeFilterAdmissionError``:
* ONE correlation: the decision, EF-5, RF-5, both RF-4 label evidences and both RF-3 feature series. RF-3 already binds
  its correlation to its EF-3 manifest and PIT dataset, so the whole admission world shares one correlation;
* ONE source world: both RF-3 feature series are computed over EF-5's exact EF-3 manifest digest, so the regime features
  read the same authenticated source packet as the preregistered strategy;
* ONE policy: RF-5, and through it both RF-4 and both RF-3, pins exactly the supplied policy's self-digest.

Membership. The policy is preregistered only when its RF-2 self-digest is a member of the sealed EF-5 V2
``registered_regime_policy_digests``, which EF-5 derives from its re-proven RF-2 snapshots and its governance approval
commits. A V1 preregistration carries no regime filter ledger, so an existing V1 record never admits a filter. A
matching feature id, policy id or content digest is never membership, and nothing the caller asserts is.

Outcome over authentic, coherent evidence (a modelled outcome, never an error), ``FAIL`` first:
* ``FAIL``: a V1 preregistration, a policy outside the ledger, an EF-5 verdict ``FAIL``, or RF-5 ``STABILITY_REJECTED``
  or ``INSUFFICIENT_OVERLAP``;
* ``NEEDS_EXTERNAL_FACTS``: EF-5 needs external facts;
* ``NEEDS_GOVERNANCE_APPROVAL``: EF-5 pending governance, an RF-2 policy without exact human governance, or RF-5
  pending governance;
* ``PASS`` otherwise. Only ``PASS`` advances, and ``regime_filter_admitted`` is True exactly then.

Membership is a digest commitment fixed when EF-5 was sealed: it does not independently prove a real-world chronological
ordering (``chronological_ordering_proven`` stays structurally False). Admission is paper evidence only: never an edge,
profitability, direction, allocation, portfolio stop, promotion, kill or quarantine decision, execution, order, capital
or readiness authorization, and never regime-conditioned performance (RF-7). ``verify_regime_filter_admission_decision``
rebuilds from the exact inputs and is total. No float, and no IO, clock, randomness, network or environment access; the
runtime ``crypto_core.regime`` package is never imported.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from typing import TypeVar, cast

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
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeLeakageBiasEvidence,
    edge_leakage_bias_evidence_from_payload,
    edge_leakage_bias_evidence_payload_is_well_formed,
    edge_leakage_bias_evidence_to_dict,
    verify_edge_leakage_bias_evidence,
)
from crypto_core.validation.regime_feature_policy import (
    REGIME_NON_CLAIM_FLAGS,
    RegimeFeaturePolicy,
    verify_regime_feature_policy,
)
from crypto_core.validation.regime_stability_evidence import (
    RegimeStabilityEvidence,
    RegimeStabilityInputs,
    RegimeStabilityStatus,
    build_regime_stability_evidence,
    regime_stability_evidence_to_dict,
)

_T = TypeVar("_T")
_PREFIX = "regime_filter_admission_decision"
_SCHEMA = "regime-filter-admission-decision.v1"
_DIGEST_FIELD = "regime_filter_admission_digest"

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "regime_filter_admission_decision_rules.v1",
    "contract_id": "EF5_RF6_REGIME_POLICY_PREREGISTRATION_ADMISSION_V1",
    "scope_rule_id": "paper_admission_of_one_preregistered_regime_filter_for_one_spec_never_edge_or_execution.v1",
    "policy_rule_id": "exact_rf2_policy_reproven_governed_only_under_exact_human_governance.v1",
    "preregistration_rule_id": "ef5_snapshot_reproven_anchor_equal_root_anchor_equal_ready_sealed_to_advance.v1",
    "membership_rule_id": "rf2_self_digest_member_of_the_sealed_ef5_v2_regime_filter_ledger_never_by_any_id.v1",
    "stability_rule_id": "rf5_rebuilt_from_its_exact_inputs_canonically_equal_same_policy_stability_proven.v1",
    "correlation_rule_id": "one_correlation_across_rf6_ef5_rf5_both_rf4_and_both_rf3.v1",
    "source_rule_id": "both_rf3_feature_series_computed_over_the_exact_ef5_ef3_manifest_digest.v1",
    "verdict_rule_id": "fail_then_needs_external_facts_then_needs_governance_approval_then_pass.v1",
    "advance_rule_id": "only_pass_advances_and_only_then_is_the_filter_admitted.v1",
    "ordering_nonclaim_rule_id": "ledger_membership_is_a_digest_commitment_never_a_real_world_chronology_proof.v1",
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
}
REGIME_FILTER_ADMISSION_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]

# RF-6 computes ``regime_filter_admitted`` (the one milestone it may set); every other regime non-claim stays a
# structural default, and chronological ordering is never claimed.
REGIME_FILTER_ADMISSION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *(flag for flag in REGIME_NON_CLAIM_FLAGS if flag[0] != "regime_filter_admitted"),
    ("chronological_ordering_proven", False),
)


def regime_filter_admission_rule_set() -> dict[str, object]:
    """A fresh copy of the RF-6 V1 rule set that ``REGIME_FILTER_ADMISSION_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


class RegimeFilterAdmissionError(EdgeArtifactError):
    """Raised on malformed input, a failed upstream re-proof, or an identity, correlation or source defect."""


@dataclass(frozen=True)
class RegimeFilterAdmissionInputs:
    """Everything RF-6 consumes; consumers re-prove a decision by rebuilding it from exactly these."""

    admission_id: str
    correlation_id: str
    policy: RegimeFeaturePolicy
    preregistration: EdgeLeakageBiasEvidence
    expected_preregistration_digest: str
    expected_root_intake_digest: str
    stability_inputs: RegimeStabilityInputs
    stability: RegimeStabilityEvidence


@dataclass(frozen=True)
class RegimeFilterAdmissionDecision:
    """Immutable, digest-bound RF-6 admission decision. Paper evidence only."""

    schema_version: str
    gate_verdict: EdgeGateVerdict
    advances: bool
    regime_filter_admitted: bool
    admission_id: str
    correlation_id: str
    root_intake_digest: str
    preregistration_id: str
    preregistration_digest: str
    preregistration_schema_version: str
    preregistration_verdict: str
    preregistration_sealed: bool
    candidate_strategy_id: str
    edge_family: str
    strategy_spec_digest: str
    strategy_id: str
    strategy_version: str
    pinned_instrument_universe: tuple[str, ...]
    source_manifest_digest: str
    regime_filter_set_digest: str
    registered_regime_policy_digests: tuple[str, ...]
    policy_id: str
    policy_version: str
    policy_digest: str
    regime_feature_policy_digest: str
    policy_governed: bool
    policy_preregistered: bool
    stability_evidence_id: str
    stability_evidence_digest: str
    stability_status: RegimeStabilityStatus
    earlier_as_of_ns: int
    later_as_of_ns: int
    label_evidence_digests: tuple[str, ...]
    feature_series_digests: tuple[str, ...]
    pit_dataset_digests: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    rule_set_id: str
    rule_set_digest: str
    regime_filter_admission_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    direction_signal_emitted: bool = False
    allocation_decided: bool = False
    portfolio_stop_authority: bool = False
    promotion_demotion_decided: bool = False
    kill_quarantine_decided: bool = False
    execution_authorized: bool = False
    order_created: bool = False
    real_orders_enabled: bool = False
    capital_allocated: bool = False
    real_capital_reserved: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    current_venue_facts_consumed: bool = False
    external_market_truth_proven: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    regime_conditioned_performance_proven: bool = False
    chronological_ordering_proven: bool = False


_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    RegimeFilterAdmissionDecision: {"gate_verdict": EdgeGateVerdict, "stability_status": RegimeStabilityStatus},
}


# --- exact input discipline -----------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> RegimeFilterAdmissionError:
    return RegimeFilterAdmissionError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _require_exact(value: object, cls: type, code: str) -> None:
    if type(value) is not cls:
        raise _fail(f"{code}_malformed")


def _require_text(value: object, name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{name}")
    return value


def _require_hex64(value: object, name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{name}_invalid")
    return cast(str, value)


def _canonically_equal(supplied: object, rebuilt: object, to_dict: Callable[..., dict]) -> bool:
    if type(supplied) is not type(rebuilt):
        return False
    try:
        return edge_canonical_json(to_dict(supplied)) == edge_canonical_json(to_dict(rebuilt))
    except Exception:  # noqa: BLE001 - an artifact that cannot serialize canonically is not the reconstruction
        return False


def _rebuild(code: str, builder: Callable[..., _T], *args: object) -> _T:
    """One accepted public builder call; any failure is a provenance defect of this decision."""

    try:
        return builder(*args)
    except Exception as exc:  # noqa: BLE001 - every reconstruction failure fails closed here
        raise _fail(f"{code}_reconstruction_failed") from exc


# --- canonical wire form --------------------------------------------------------------------------------------------


def _serialize(value: object) -> object:
    if type(value) is tuple:
        return [_serialize(item) for item in cast(tuple, value)]
    if type(value) is int:
        if 0 <= cast(int, value) <= _MAX_WIRE_INT:
            return value
        raise _fail("payload_integer_out_of_range")
    if type(value) is str or type(value) is bool:
        return value
    raise _fail("payload_value_not_canonical")


def _payload(artifact: object) -> dict[str, object]:
    """The exact wire form: an enum field holds its exact member, everything else exact tuples and scalars."""

    enums = _ENUM_FIELDS.get(type(artifact), {})
    payload: dict[str, object] = {}
    for item in fields(artifact):  # type: ignore[arg-type]
        value = getattr(artifact, item.name)
        enum_cls = enums.get(item.name)
        if enum_cls is None:
            payload[item.name] = _serialize(value)
        elif type(value) is enum_cls:
            payload[item.name] = cast(Enum, value).value
        else:
            raise _fail("payload_enum_field_not_exact_member")
    return payload


# --- upstream authority ---------------------------------------------------------------------------------------------


def _require_policy(value: object) -> RegimeFeaturePolicy:
    _require_exact(value, RegimeFeaturePolicy, "policy")
    if not verify_regime_feature_policy(value).intact:
        raise _fail("policy_not_intact")
    return cast(RegimeFeaturePolicy, value)


def _require_preregistration(
    value: object, anchor: object, root_anchor: object, *, correlation_id: str
) -> EdgeLeakageBiasEvidence:
    """The exact EF-5 artifact, read back from its canonical snapshot, re-proven, anchored, rooted and READY."""

    _require_exact(value, EdgeLeakageBiasEvidence, "preregistration")
    root = _require_hex64(root_anchor, "expected_root_intake_digest")
    try:
        snapshot_payload = edge_leakage_bias_evidence_to_dict(cast(EdgeLeakageBiasEvidence, value))
    except Exception as exc:  # noqa: BLE001 - an EF-5 object that cannot serialize is never authority
        raise _fail("preregistration_not_serializable") from exc
    binding = build_edge_authority_binding(
        snapshot_payload=snapshot_payload,
        expected_digest=anchor,
        shape=edge_leakage_bias_evidence_payload_is_well_formed,
        error=RegimeFilterAdmissionError,
        code=_reason("preregistration"),
    )
    preregistration = edge_leakage_bias_evidence_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_leakage_bias_evidence(preregistration)
    if not verification.intact:
        raise _fail("preregistration_not_intact")
    if verification.recomputed_digest != binding.expected_digest:
        raise _fail("preregistration_digest_mismatch")
    if preregistration.root_intake_digest != root:
        raise _fail("preregistration_root_intake_mismatch")
    if preregistration.correlation_id != correlation_id:
        raise _fail("preregistration_correlation_mismatch")
    if preregistration.status is not EdgeEvidenceStatus.READY:
        raise _fail("preregistration_rejected")
    return preregistration


def _prove_stability(inputs: object, evidence: object, policy: RegimeFeaturePolicy) -> RegimeStabilityEvidence:
    """RF-5 rebuilt from its exact inputs, canonically equal to the supplied evidence and bound to the same policy."""

    _require_exact(inputs, RegimeStabilityInputs, "stability_inputs")
    _require_exact(evidence, RegimeStabilityEvidence, "stability")
    rebuilt = _rebuild("stability", build_regime_stability_evidence, inputs)
    if not _canonically_equal(evidence, rebuilt, regime_stability_evidence_to_dict):
        raise _fail("stability_not_reconstructed")
    if rebuilt.regime_feature_policy_digest != policy.regime_feature_policy_digest:
        raise _fail("stability_policy_mismatch")
    return rebuilt


def _bind_admission_world(
    inputs: RegimeStabilityInputs,
    stability: RegimeStabilityEvidence,
    preregistration: EdgeLeakageBiasEvidence,
    *,
    correlation_id: str,
) -> tuple[tuple[str, str], tuple[str, str], tuple[str, str]]:
    """One correlation and one EF-3 source world across RF-5, both RF-4 and both RF-3; returns their digests.

    RF-5's rebuild already proved each carried RF-4 and RF-3 evidence canonically equal to its own reconstruction.
    """

    if stability.correlation_id != correlation_id:
        raise _fail("stability_correlation_mismatch")
    labels, series, datasets = [], [], []
    for side, label_inputs, label_evidence in (
        ("earlier", inputs.earlier_label_inputs, inputs.earlier_labels),
        ("later", inputs.later_label_inputs, inputs.later_labels),
    ):
        feature_series = label_inputs.feature_series
        if label_evidence.correlation_id != correlation_id:
            raise _fail(f"{side}_labels_correlation_mismatch")
        if feature_series.correlation_id != correlation_id:
            raise _fail(f"{side}_feature_series_correlation_mismatch")
        if feature_series.source_manifest_digest != preregistration.source_manifest_digest:
            raise _fail(f"{side}_feature_series_source_manifest_mismatch")
        labels.append(label_evidence.label_evidence_digest)
        series.append(feature_series.feature_series_digest)
        datasets.append(feature_series.pit_dataset_digest)
    return (labels[0], labels[1]), (series[0], series[1]), (datasets[0], datasets[1])


# --- the decision ---------------------------------------------------------------------------------------------------


def _preregistration_reasons(preregistration: EdgeLeakageBiasEvidence) -> tuple[list[str], list[str], list[str]]:
    """``(fail, needs_external, needs_governance)`` of an EF-5 that is not sealed."""

    sealed = (
        preregistration.gate_verdict is EdgeGateVerdict.PASS
        and preregistration.advances is True
        and preregistration.preregistration_sealed is True
    )
    if sealed:
        return [], [], []
    code = _reason(f"preregistration_not_sealed:{preregistration.gate_verdict.value}")
    if preregistration.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
        return [], [code], []
    if preregistration.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
        return [], [], [code]
    return [code], [], []


_STABILITY_REASONS: dict[RegimeStabilityStatus, tuple[int, str]] = {
    RegimeStabilityStatus.STABILITY_REJECTED: (0, "stability_rejected"),
    RegimeStabilityStatus.INSUFFICIENT_OVERLAP: (0, "stability_insufficient_overlap"),
    RegimeStabilityStatus.NEEDS_GOVERNANCE_APPROVAL: (2, "stability_needs_governance_approval"),
}


def build_regime_filter_admission_decision(inputs: RegimeFilterAdmissionInputs) -> RegimeFilterAdmissionDecision:
    """Decide whether the exact policy is admitted as a regime filter for the exact EF-5-preregistered spec.

    Malformed input, every failed upstream re-proof and every identity, correlation or source defect raise
    ``RegimeFilterAdmissionError``. A missing membership, an unsealed preregistration, missing governance or an
    unproven stability are modelled outcomes, never errors. Inputs are never mutated.
    """

    _require_exact(inputs, RegimeFilterAdmissionInputs, "inputs")
    admission_id = _require_text(inputs.admission_id, "admission_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    policy = _require_policy(inputs.policy)
    preregistration = _require_preregistration(
        inputs.preregistration,
        inputs.expected_preregistration_digest,
        inputs.expected_root_intake_digest,
        correlation_id=correlation_id,
    )
    stability = _prove_stability(inputs.stability_inputs, inputs.stability, policy)
    label_digests, series_digests, dataset_digests = _bind_admission_world(
        inputs.stability_inputs, stability, preregistration, correlation_id=correlation_id
    )

    buckets: tuple[list[str], list[str], list[str]] = _preregistration_reasons(preregistration)
    preregistered = policy.regime_feature_policy_digest in preregistration.registered_regime_policy_digests
    if not preregistration.regime_filter_bindings:
        buckets[0].append(_reason("preregistration_has_no_regime_filter_ledger"))
    elif not preregistered:
        buckets[0].append(_reason("regime_policy_not_preregistered"))
    if not policy.advances:
        buckets[2].append(_reason("policy_needs_governance_approval"))
    if stability.status in _STABILITY_REASONS:
        bucket, code = _STABILITY_REASONS[stability.status]
        buckets[bucket].append(_reason(code))
    fail, needs_external, needs_governance = buckets
    verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
    advances = verdict is EdgeGateVerdict.PASS

    seed = RegimeFilterAdmissionDecision(
        schema_version=_SCHEMA,
        gate_verdict=verdict,
        advances=advances,
        regime_filter_admitted=advances,
        admission_id=admission_id,
        correlation_id=correlation_id,
        root_intake_digest=preregistration.root_intake_digest,
        preregistration_id=preregistration.preregistration_id,
        preregistration_digest=preregistration.leakage_bias_evidence_digest,
        preregistration_schema_version=preregistration.schema_version,
        preregistration_verdict=preregistration.gate_verdict.value,
        preregistration_sealed=preregistration.preregistration_sealed,
        candidate_strategy_id=preregistration.candidate_strategy_id,
        edge_family=preregistration.edge_family,
        strategy_spec_digest=preregistration.strategy_spec_digest,
        strategy_id=preregistration.strategy_id,
        strategy_version=preregistration.strategy_version,
        pinned_instrument_universe=preregistration.pinned_instrument_universe,
        source_manifest_digest=preregistration.source_manifest_digest,
        regime_filter_set_digest=preregistration.regime_filter_set_digest,
        registered_regime_policy_digests=preregistration.registered_regime_policy_digests,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        policy_digest=policy.policy_digest,
        regime_feature_policy_digest=policy.regime_feature_policy_digest,
        policy_governed=policy.advances,
        policy_preregistered=preregistered,
        stability_evidence_id=stability.stability_evidence_id,
        stability_evidence_digest=stability.stability_evidence_digest,
        stability_status=stability.status,
        earlier_as_of_ns=stability.earlier_as_of_ns,
        later_as_of_ns=stability.later_as_of_ns,
        label_evidence_digests=label_digests,
        feature_series_digests=series_digests,
        pit_dataset_digests=dataset_digests,
        verdict_reason_codes=_sorted_unique([*fail, *needs_external, *needs_governance]),
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=REGIME_FILTER_ADMISSION_RULE_SET_DIGEST,
        regime_filter_admission_digest="",
    )
    return replace(seed, regime_filter_admission_digest=edge_payload_digest(_payload(seed), _DIGEST_FIELD))


def regime_filter_admission_decision_to_dict(decision: RegimeFilterAdmissionDecision) -> dict[str, object]:
    """Canonical JSON-ready mapping of a decision, its self-digest included."""

    return _payload(decision)


def regime_filter_admission_decision_digest(decision: RegimeFilterAdmissionDecision) -> str:
    """Recompute the canonical decision digest, excluding only ``regime_filter_admission_digest``."""

    return edge_payload_digest(_payload(decision), _DIGEST_FIELD)


def verify_regime_filter_admission_decision(
    decision: object, inputs: RegimeFilterAdmissionInputs
) -> EdgeEvidenceVerification:
    """Re-prove a decision by rebuilding it, every upstream re-proof included, from its exact inputs. Total."""

    stage = "decision_type_invalid"
    try:
        if type(decision) is not RegimeFilterAdmissionDecision:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "decision_serialization_failed"
        carried = _payload(decision)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _DIGEST_FIELD)
        stage = "decision_reconstruction_failed"
        expected = _payload(build_regime_filter_admission_decision(inputs))
        codes = {_reason("self_digest_mismatch")} if carried[_DIGEST_FIELD] != recomputed else set()
        for name in set(expected) | set(carried):
            if name not in expected or name not in carried:
                codes.add(_reason(f"field_mismatch:{name}"))
            elif edge_canonical_json(expected[name]) != edge_canonical_json(carried[name]):
                codes.add(_reason(f"field_mismatch:{name}"))
        reason_codes = tuple(sorted(codes))
        return EdgeEvidenceVerification(not reason_codes, reason_codes, recomputed, canonical)
    except Exception:  # noqa: BLE001 - VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT
        return EdgeEvidenceVerification(False, (_reason(stage),), "", "")


__all__ = [
    "REGIME_FILTER_ADMISSION_NON_CLAIM_FLAGS",
    "REGIME_FILTER_ADMISSION_RULE_SET_DIGEST",
    "RegimeFilterAdmissionDecision",
    "RegimeFilterAdmissionError",
    "RegimeFilterAdmissionInputs",
    "build_regime_filter_admission_decision",
    "regime_filter_admission_decision_digest",
    "regime_filter_admission_decision_to_dict",
    "regime_filter_admission_rule_set",
    "verify_regime_filter_admission_decision",
]
