"""RF-5 dual-as-of no-repaint and stability evidence (RF5_REGIME_STABILITY_EVIDENCE_V1).

Design authority: ``docs/crypto_core/regime_volatility_filter_design.md`` section 1 (RF-5), under the controller
structural authority ``RF_CORE_FORMULA_LABEL_AND_STABILITY_POLICY_V1`` (closure
``RF2_RF5_CORE_PIT_REGIME_EVIDENCE_SPINE_V1``). This is the repaint proof.

Inputs. RF-5 consumes TWO RF-4 label evidences, each rebuilt from its exact inputs and canonically equal, and both bound
to the same exact RF-2 policy (self-digest), which is re-proven through its total verifier. Their as-of coordinates are
UTC-day aligned:
* the earlier as-of must be strictly before the later one, so a same or reversed pair raises;
* the gap in whole UTC days must reach ``stability_min_asof_gap_days``, inclusive, or the pair raises.

No-repaint. The overlap is the exact intersection of the two label-day windows. On EVERY overlapping day the earlier and
later labels (``UNLABELED`` included) must be exactly identical: ONE mismatch is ``STABILITY_REJECTED``. There is no
tolerance and no relabeling. The later evidence may label additional later days, but may never change a historical
one.

Distribution drift (``RF5_TOTAL_VARIATION_LABEL_DISTRIBUTION_DRIFT_V1``). Each evidence's distribution covers its FULL
label window over the closed vocabulary (the policy label set plus ``UNLABELED``, a member absent on one side counting
zero): ``p_i = count_i / earlier_days`` and ``q_i = count_i / later_days``. The exact total variation distance is
``TVD = 1/2 * sum_i |p_i - q_i|`` in ``Fraction``. It is published exactly as reduced ``p/q`` text and rendered
half-even at scale 18. ``TVD <= distribution_drift_cap`` passes (equality passes), compared exactly. A breach rejects
even when every overlapping day matches.

Outcome (the stability methodology alone):
* ``STABILITY_REJECTED`` on any repaint or drift breach;
* otherwise ``INSUFFICIENT_OVERLAP`` when the overlap is below ``stability_min_overlap_days``;
* otherwise ``STABILITY_PROVEN``.

Terminal status, first match wins:
1. ``STABILITY_REJECTED`` when the outcome is rejected or either label evidence ``FAIL``s its own UNLABELED cap;
2. ``INSUFFICIENT_OVERLAP``;
3. ``NEEDS_GOVERNANCE_APPROVAL`` when the policy lacks exact human governance: an ungoverned policy never masquerades
   as ``STABILITY_PROVEN``;
4. ``STABILITY_PROVEN``.

Only ``STABILITY_PROVEN`` advances. Malformed input and every provenance or as-of defect raise
``RegimeStabilityEvidenceError``. ``verify_regime_stability_evidence`` rebuilds from the exact inputs and is total.

Paper evidence only: no admission (RF-6), conditioned performance (RF-7), edge, direction, allocation, stop, order,
capital or readiness claim. No float, and no IO, clock, randomness, network or environment access. The runtime
``crypto_core.regime`` package is never imported.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction
from typing import TypeVar, cast

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
)
from crypto_core.validation.regime_feature_policy import (
    REGIME_NON_CLAIM_FLAGS,
    REGIME_UNLABELED,
    RegimeFeaturePolicy,
    regime_decimal_text,
    regime_decimal_value,
    verify_regime_feature_policy,
)
from crypto_core.validation.regime_label_evidence import (
    RegimeLabelEvidence,
    RegimeLabelInputs,
    build_regime_label_evidence,
    regime_label_evidence_to_dict,
)

_T = TypeVar("_T")
_PREFIX = "regime_stability_evidence"
_SCHEMA = "regime-stability-evidence.v1"
_DIGEST_FIELD = "stability_evidence_digest"
REGIME_DRIFT_METHODOLOGY_ID = "RF5_TOTAL_VARIATION_LABEL_DISTRIBUTION_DRIFT_V1"

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "regime_stability_evidence_rules.v1",
    "contract_id": "RF2_RF5_CORE_PIT_REGIME_EVIDENCE_SPINE_V1",
    "structural_authority_id": "RF_CORE_FORMULA_LABEL_AND_STABILITY_POLICY_V1",
    "scope_rule_id": "paper_repaint_and_stability_proof_never_admission_conditioned_performance_or_execution.v1",
    "input_rule_id": "exact_rf2_policy_reproven_two_rf4_rebuilt_from_their_inputs_same_exact_policy.v1",
    "as_of_rule_id": "utc_day_aligned_earlier_as_of_strictly_before_later_gap_in_days_at_least_governed_minimum.v1",
    "overlap_rule_id": "exact_intersection_of_the_two_label_day_windows.v1",
    "repaint_rule_id": "every_overlapping_day_label_exactly_identical_one_mismatch_rejects_no_tolerance.v1",
    "drift_methodology_id": REGIME_DRIFT_METHODOLOGY_ID,
    "drift_rule_id": "exact_half_sum_abs_difference_over_label_set_and_unlabeled_full_windows_at_most_cap_passes.v1",
    "outcome_rule_id": "rejected_on_repaint_or_drift_breach_else_insufficient_overlap_else_proven.v1",
    "status_rule_id": (
        "rejected_also_when_a_label_evidence_fails_its_cap_then_insufficient_overlap_then_needs_governance_approval"
        "_then_proven.v1"
    ),
    "advance_rule_id": "only_stability_proven_advances.v1",
    "unlabeled_label_id": REGIME_UNLABELED,
    "utc_day_ns": 86_400_000_000_000,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
}
REGIME_STABILITY_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
_DAY_NS: int = _RULE_SET_V1["utc_day_ns"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]


def regime_stability_rule_set() -> dict[str, object]:
    """A fresh copy of the RF-5 V1 rule set that ``REGIME_STABILITY_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


class RegimeStabilityEvidenceError(EdgeArtifactError):
    """A malformed input or any provenance or as-of defect: an invalid stability evidence is never represented."""


class RegimeStabilityOutcome(str, Enum):
    """The stability methodology alone: repaint, drift and overlap."""

    STABILITY_PROVEN = "STABILITY_PROVEN"
    STABILITY_REJECTED = "STABILITY_REJECTED"
    INSUFFICIENT_OVERLAP = "INSUFFICIENT_OVERLAP"


class RegimeStabilityStatus(str, Enum):
    """The terminal status; only ``STABILITY_PROVEN`` advances."""

    STABILITY_PROVEN = "STABILITY_PROVEN"
    STABILITY_REJECTED = "STABILITY_REJECTED"
    INSUFFICIENT_OVERLAP = "INSUFFICIENT_OVERLAP"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


@dataclass(frozen=True)
class RegimeStabilityInputs:
    """Everything RF-5 consumes; consumers re-prove an evidence by rebuilding it from exactly these."""

    stability_evidence_id: str
    correlation_id: str
    policy: RegimeFeaturePolicy
    earlier_label_inputs: RegimeLabelInputs
    earlier_labels: RegimeLabelEvidence
    later_label_inputs: RegimeLabelInputs
    later_labels: RegimeLabelEvidence


@dataclass(frozen=True)
class RegimeLabelDistributionEntry:
    """One vocabulary member's day count in each full label window."""

    label_id: str
    earlier_day_count: int
    later_day_count: int


@dataclass(frozen=True)
class RegimeStabilityEvidence:
    """Immutable, digest-bound RF-5 no-repaint and stability evidence. Paper evidence only."""

    schema_version: str
    status: RegimeStabilityStatus
    stability_outcome: RegimeStabilityOutcome
    advances: bool
    policy_governed: bool
    stability_evidence_id: str
    correlation_id: str
    policy_id: str
    policy_version: str
    regime_feature_policy_digest: str
    earlier_label_evidence_digest: str
    later_label_evidence_digest: str
    earlier_label_verdict: str
    later_label_verdict: str
    earlier_as_of_ns: int
    later_as_of_ns: int
    as_of_gap_days: int
    stability_min_asof_gap_days: int
    earlier_first_day_index: int
    earlier_last_day_index: int
    later_first_day_index: int
    later_last_day_index: int
    overlap_first_day_index: int | None
    overlap_last_day_index: int | None
    overlap_day_count: int
    stability_min_overlap_days: int
    repaint_mismatch_day_indices: tuple[int, ...]
    distribution: tuple[RegimeLabelDistributionEntry, ...]
    earlier_label_day_count: int
    later_label_day_count: int
    distribution_drift: str
    distribution_drift_exact: str
    distribution_drift_cap: str
    drift_within_cap: bool
    drift_methodology_id: str
    reason_codes: tuple[str, ...]
    rule_set_id: str
    rule_set_digest: str
    stability_evidence_digest: str
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
    regime_filter_admitted: bool = False
    regime_conditioned_performance_proven: bool = False


REGIME_STABILITY_NON_CLAIM_FLAGS = REGIME_NON_CLAIM_FLAGS
_RECORD_TYPES = frozenset({RegimeLabelDistributionEntry})
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    RegimeStabilityEvidence: {"status": RegimeStabilityStatus, "stability_outcome": RegimeStabilityOutcome},
}


# --- exact input discipline -----------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> RegimeStabilityEvidenceError:
    return RegimeStabilityEvidenceError(_reason(code))


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


def _canonically_equal(supplied: object, rebuilt: object, to_dict: Callable[..., dict]) -> bool:
    if type(supplied) is not type(rebuilt):
        return False
    try:
        return edge_canonical_json(to_dict(supplied)) == edge_canonical_json(to_dict(rebuilt))
    except Exception:  # noqa: BLE001 - an artifact that cannot serialize canonically is not the reconstruction
        return False


def _rebuild(code: str, builder: Callable[..., _T], *args: object) -> _T:
    """One accepted public builder call; any failure is a provenance defect of this evidence."""

    try:
        return builder(*args)
    except Exception as exc:  # noqa: BLE001 - every reconstruction failure fails closed here
        raise _fail(f"{code}_reconstruction_failed") from exc


# --- the drift ------------------------------------------------------------------------------------------------------


def measure_regime_label_distribution_drift(earlier_counts: Sequence[int], later_counts: Sequence[int]) -> Fraction:
    """The exact total variation distance between two label distributions over one aligned vocabulary.

    ``earlier_counts[i]`` and ``later_counts[i]`` count the same vocabulary member. Every count is a non-negative int
    and each side has at least one day. Malformed input raises.
    """

    earlier = tuple(earlier_counts) if type(earlier_counts) in (tuple, list) else None
    later = tuple(later_counts) if type(later_counts) in (tuple, list) else None
    if earlier is None or later is None or len(earlier) != len(later) or not earlier:
        raise _fail("drift_counts_malformed")
    if any(type(count) is not int or count < 0 for count in (*earlier, *later)):
        raise _fail("drift_counts_malformed")
    earlier_total, later_total = sum(earlier), sum(later)
    if earlier_total == 0 or later_total == 0:
        raise _fail("drift_counts_malformed")
    distance = sum(
        (abs(Fraction(left, earlier_total) - Fraction(right, later_total)) for left, right in zip(earlier, later)),
        Fraction(0),
    )
    return distance / 2


# --- canonical wire form --------------------------------------------------------------------------------------------


def _serialize(value: object) -> object:
    if type(value) in _RECORD_TYPES:
        return _payload(value)
    if type(value) is tuple:
        return [_serialize(item) for item in cast(tuple, value)]
    if type(value) is int:
        if 0 <= cast(int, value) <= _MAX_WIRE_INT:
            return value
        raise _fail("payload_integer_out_of_range")
    if value is None or type(value) is str or type(value) is bool:
        return value
    raise _fail("payload_value_not_canonical")


def _payload(artifact: object) -> dict[str, object]:
    """The exact wire form: an enum field holds its exact member, everything else exact records and scalars."""

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


# --- the evidence ---------------------------------------------------------------------------------------------------


def _require_policy(value: object) -> RegimeFeaturePolicy:
    _require_exact(value, RegimeFeaturePolicy, "policy")
    if not verify_regime_feature_policy(value).intact:
        raise _fail("policy_not_intact")
    return cast(RegimeFeaturePolicy, value)


def _prove_labels(side: str, inputs: object, evidence: object, policy: RegimeFeaturePolicy) -> RegimeLabelEvidence:
    """One RF-4 rebuilt from its exact inputs, canonically equal to the supplied evidence, on the same exact policy."""

    _require_exact(inputs, RegimeLabelInputs, f"{side}_label_inputs")
    _require_exact(evidence, RegimeLabelEvidence, f"{side}_labels")
    rebuilt = _rebuild(f"{side}_labels", build_regime_label_evidence, inputs)
    if not _canonically_equal(evidence, rebuilt, regime_label_evidence_to_dict):
        raise _fail(f"{side}_labels_not_reconstructed")
    if rebuilt.regime_feature_policy_digest != policy.regime_feature_policy_digest:
        raise _fail(f"{side}_labels_policy_mismatch")
    return rebuilt


def _status(outcome: RegimeStabilityOutcome, label_failed: bool, governed: bool) -> RegimeStabilityStatus:
    """Rejection first, then insufficient overlap; governance only ever withholds a proven outcome."""

    if outcome is RegimeStabilityOutcome.STABILITY_REJECTED or label_failed:
        return RegimeStabilityStatus.STABILITY_REJECTED
    if outcome is RegimeStabilityOutcome.INSUFFICIENT_OVERLAP:
        return RegimeStabilityStatus.INSUFFICIENT_OVERLAP
    if not governed:
        return RegimeStabilityStatus.NEEDS_GOVERNANCE_APPROVAL
    return RegimeStabilityStatus.STABILITY_PROVEN


def build_regime_stability_evidence(inputs: RegimeStabilityInputs) -> RegimeStabilityEvidence:
    """Prove or refute no-repaint stability of one policy's labels across two as-of coordinates.

    Malformed input and every provenance or as-of defect raise ``RegimeStabilityEvidenceError``. A repaint, a drift
    breach, an insufficient overlap or a policy without exact human governance are modelled outcomes, never errors.
    Inputs are never mutated.
    """

    _require_exact(inputs, RegimeStabilityInputs, "inputs")
    stability_evidence_id = _require_text(inputs.stability_evidence_id, "stability_evidence_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    policy = _require_policy(inputs.policy)
    earlier = _prove_labels("earlier", inputs.earlier_label_inputs, inputs.earlier_labels, policy)
    later = _prove_labels("later", inputs.later_label_inputs, inputs.later_labels, policy)

    if later.as_of_ns <= earlier.as_of_ns:
        raise _fail("as_of_not_strictly_increasing")
    gap_days = (later.as_of_ns - earlier.as_of_ns) // _DAY_NS
    if gap_days < policy.stability_min_asof_gap_days:
        raise _fail("as_of_gap_below_governed_minimum")

    overlap_first = max(earlier.first_label_day_index, later.first_label_day_index)
    overlap_last = min(earlier.last_label_day_index, later.last_label_day_index)
    overlap = range(overlap_first, overlap_last + 1)
    earlier_by_day = {label.day_index: label.label_id for label in earlier.labels}
    later_by_day = {label.day_index: label.label_id for label in later.labels}
    mismatches = tuple(day for day in overlap if earlier_by_day[day] != later_by_day[day])

    vocabulary = (*policy.label_set, REGIME_UNLABELED)
    earlier_counts = {count.label_id: count.day_count for count in earlier.label_counts}
    later_counts = {count.label_id: count.day_count for count in later.label_counts}
    if set(earlier_counts) != set(vocabulary) or set(later_counts) != set(vocabulary):
        raise _fail("label_counts_vocabulary_mismatch")
    drift = measure_regime_label_distribution_drift(
        [earlier_counts[label] for label in vocabulary], [later_counts[label] for label in vocabulary]
    )
    cap = regime_decimal_value(policy.distribution_drift_cap)
    drift_text = regime_decimal_text(drift)
    if cap is None or drift_text is None:
        raise _fail("drift_not_representable")
    within = drift <= cap

    reasons: list[str] = []
    if mismatches:
        reasons.append(_reason("repaint_detected"))
    if not within:
        reasons.append(_reason("distribution_drift_above_cap"))
    if len(overlap) < policy.stability_min_overlap_days:
        reasons.append(_reason("overlap_below_governed_minimum"))
    if mismatches or not within:
        outcome = RegimeStabilityOutcome.STABILITY_REJECTED
    elif len(overlap) < policy.stability_min_overlap_days:
        outcome = RegimeStabilityOutcome.INSUFFICIENT_OVERLAP
    else:
        outcome = RegimeStabilityOutcome.STABILITY_PROVEN
    label_failed = False
    for side, labels in (("earlier", earlier), ("later", later)):
        if labels.gate_verdict is EdgeGateVerdict.FAIL:
            label_failed = True
            reasons.append(_reason(f"{side}_label_evidence_failed"))
    if not policy.advances:
        reasons.append(_reason("policy_needs_governance_approval"))
    status = _status(outcome, label_failed, policy.advances)

    seed = RegimeStabilityEvidence(
        schema_version=_SCHEMA,
        status=status,
        stability_outcome=outcome,
        advances=status is RegimeStabilityStatus.STABILITY_PROVEN,
        policy_governed=policy.advances,
        stability_evidence_id=stability_evidence_id,
        correlation_id=correlation_id,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        regime_feature_policy_digest=policy.regime_feature_policy_digest,
        earlier_label_evidence_digest=earlier.label_evidence_digest,
        later_label_evidence_digest=later.label_evidence_digest,
        earlier_label_verdict=earlier.gate_verdict.value,
        later_label_verdict=later.gate_verdict.value,
        earlier_as_of_ns=earlier.as_of_ns,
        later_as_of_ns=later.as_of_ns,
        as_of_gap_days=gap_days,
        stability_min_asof_gap_days=policy.stability_min_asof_gap_days,
        earlier_first_day_index=earlier.first_label_day_index,
        earlier_last_day_index=earlier.last_label_day_index,
        later_first_day_index=later.first_label_day_index,
        later_last_day_index=later.last_label_day_index,
        overlap_first_day_index=overlap_first if overlap else None,
        overlap_last_day_index=overlap_last if overlap else None,
        overlap_day_count=len(overlap),
        stability_min_overlap_days=policy.stability_min_overlap_days,
        repaint_mismatch_day_indices=mismatches,
        distribution=tuple(
            RegimeLabelDistributionEntry(label, earlier_counts[label], later_counts[label]) for label in vocabulary
        ),
        earlier_label_day_count=earlier.label_day_count,
        later_label_day_count=later.label_day_count,
        distribution_drift=drift_text,
        distribution_drift_exact=f"{drift.numerator}/{drift.denominator}",
        distribution_drift_cap=policy.distribution_drift_cap,
        drift_within_cap=within,
        drift_methodology_id=REGIME_DRIFT_METHODOLOGY_ID,
        reason_codes=_sorted_unique(reasons),
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=REGIME_STABILITY_RULE_SET_DIGEST,
        stability_evidence_digest="",
    )
    return replace(seed, stability_evidence_digest=edge_payload_digest(_payload(seed), _DIGEST_FIELD))


def regime_stability_evidence_to_dict(evidence: RegimeStabilityEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of an evidence, its self-digest included."""

    return _payload(evidence)


def regime_stability_evidence_digest(evidence: RegimeStabilityEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``stability_evidence_digest``."""

    return edge_payload_digest(_payload(evidence), _DIGEST_FIELD)


def verify_regime_stability_evidence(evidence: object, inputs: RegimeStabilityInputs) -> EdgeEvidenceVerification:
    """Re-prove an evidence by rebuilding it, every upstream re-proof included, from its exact inputs. Total."""

    stage = "evidence_type_invalid"
    try:
        if type(evidence) is not RegimeStabilityEvidence:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _payload(evidence)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _DIGEST_FIELD)
        stage = "evidence_reconstruction_failed"
        expected = _payload(build_regime_stability_evidence(inputs))
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
    "REGIME_DRIFT_METHODOLOGY_ID",
    "REGIME_STABILITY_NON_CLAIM_FLAGS",
    "REGIME_STABILITY_RULE_SET_DIGEST",
    "RegimeLabelDistributionEntry",
    "RegimeStabilityEvidence",
    "RegimeStabilityEvidenceError",
    "RegimeStabilityInputs",
    "RegimeStabilityOutcome",
    "RegimeStabilityStatus",
    "build_regime_stability_evidence",
    "measure_regime_label_distribution_drift",
    "regime_stability_evidence_digest",
    "regime_stability_evidence_to_dict",
    "regime_stability_rule_set",
    "verify_regime_stability_evidence",
]
