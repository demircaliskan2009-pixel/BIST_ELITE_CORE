"""Tests for the RF-5 dual-as-of no-repaint and stability evidence (``regime_stability_evidence``).

Fixtures: the RF-4 test module's up/down worlds. An earlier evidence labels the first ``m`` moves of a history as of
the start of day ``D0 + 1 + m``, and a later one labels its first ``n`` moves as of ``D0 + 1 + n``. Both windows start
at ``D0 + 2``, so the overlap is ``m`` days and the as-of gap is ``n - m`` days. Expected labels, mismatches and every
total variation distance are recomputed here from the move strings with plain ``Fraction`` arithmetic, never by the
module. Every value is a SYNTHETIC TEST VALUE.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import re
from collections.abc import Sequence
from dataclasses import fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.regime_stability_evidence as stability_module
from crypto_core.validation.edge_artifact_core import EdgeGateVerdict, edge_canonical_json, edge_sha256_text
from crypto_core.validation.regime_feature_policy import REGIME_NON_CLAIM_FLAGS, REGIME_UNLABELED, RegimeFeaturePolicy
from crypto_core.validation.regime_label_evidence import regime_label_evidence_digest
from crypto_core.validation.regime_stability_evidence import (
    REGIME_DRIFT_METHODOLOGY_ID,
    REGIME_STABILITY_RULE_SET_DIGEST,
    RegimeLabelDistributionEntry,
    RegimeStabilityEvidence,
    RegimeStabilityEvidenceError,
    RegimeStabilityInputs,
    RegimeStabilityOutcome,
    RegimeStabilityStatus,
    build_regime_stability_evidence,
    measure_regime_label_distribution_drift,
    regime_stability_evidence_digest,
    regime_stability_evidence_to_dict,
    regime_stability_rule_set,
    verify_regime_stability_evidence,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

try:  # the module objects pytest collects (basename import), so cached fixtures are shared with their own tests
    import test_regime_feature_policy as rf2t
    import test_regime_label_evidence as rf4t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_regime_feature_policy as rf2t
    from tests.crypto_core.validation import test_regime_label_evidence as rf4t

_PREFIX = "regime_stability_evidence"
SOURCE = Path(stability_module.__file__).read_text(encoding="utf-8")
DAY, D0 = rf4t.DAY, rf4t.D0
PROVEN = RegimeStabilityStatus.STABILITY_PROVEN
REJECTED = RegimeStabilityStatus.STABILITY_REJECTED
INSUFFICIENT = RegimeStabilityStatus.INSUFFICIENT_OVERLAP
NEEDS_GOVERNANCE = RegimeStabilityStatus.NEEDS_GOVERNANCE_APPROVAL
VOCABULARY = ("CALM", "STRESSED", REGIME_UNLABELED)
d = rf2t.d


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def refused(text: str):
    """``pytest.raises`` for one exact RF-5 construction error."""

    return pytest.raises(RegimeStabilityEvidenceError, match=f"^{re.escape(code(text))}$")


def stability_policy(**overrides: object) -> RegimeFeaturePolicy:
    """SYNTHETIC: overlap of at least 3 days, an as-of gap of at least 1 day, drift at most 0.25."""

    values: dict[str, object] = {
        "stability_min_overlap_days": 3,
        "stability_min_asof_gap_days": 1,
        "distribution_drift_cap": d("0.25"),
    }
    values.update(overrides)
    return rf4t.updown_policy(**values)  # type: ignore[arg-type]


def stability_inputs(
    earlier_moves: str,
    later_moves: str,
    *,
    policy: RegimeFeaturePolicy | None = None,
    later_policy: RegimeFeaturePolicy | None = None,
    drop_days: tuple[int, ...] = (),
    **overrides: object,
) -> RegimeStabilityInputs:
    policy = stability_policy() if policy is None else policy
    earlier = rf4t.label_inputs(earlier_moves, policy=policy, drop_days=drop_days)
    later = rf4t.label_inputs(later_moves, policy=policy if later_policy is None else later_policy, drop_days=drop_days)
    values: dict[str, object] = {
        "stability_evidence_id": "rf5-synthetic-1",
        "correlation_id": "corr-rf5",
        "policy": policy,
        "earlier_label_inputs": earlier,
        "earlier_labels": rf4t.build(earlier),
        "later_label_inputs": later,
        "later_labels": rf4t.build(later),
    }
    values.update(overrides)
    return RegimeStabilityInputs(**values)  # type: ignore[arg-type]


def build(inputs: object) -> RegimeStabilityEvidence:
    return build_regime_stability_evidence(inputs)  # type: ignore[arg-type]


def decide(inputs: RegimeStabilityInputs) -> RegimeStabilityEvidence:
    """Build, then re-prove by reconstruction: every evidence a test reads is intact."""

    evidence = build(inputs)
    verification = verify_regime_stability_evidence(evidence, inputs)
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert verification.recomputed_digest == evidence.stability_evidence_digest
    assert json.loads(verification.canonical_json) == regime_stability_evidence_to_dict(evidence)
    assert {name: getattr(evidence, name) for name, _ in REGIME_NON_CLAIM_FLAGS} == dict(REGIME_NON_CLAIM_FLAGS)
    assert evidence.advances is (evidence.status is PROVEN)
    return evidence


def reseal(evidence: RegimeStabilityEvidence, **changes: object) -> RegimeStabilityEvidence:
    changed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(changed, stability_evidence_digest=regime_stability_evidence_digest(changed))


def oracle_counts(labels: Sequence[str]) -> list[int]:
    return [list(labels).count(label) for label in VOCABULARY]


def oracle_tvd(earlier: Sequence[str], later: Sequence[str]) -> Fraction:
    """``1/2 * sum |p_i - q_i|`` over CALM, STRESSED and UNLABELED, from plain counts."""

    left, right = oracle_counts(earlier), oracle_counts(later)
    total_left, total_right = sum(left), sum(right)
    return sum((abs(Fraction(a, total_left) - Fraction(b, total_right)) for a, b in zip(left, right)), Fraction(0)) / 2


# --- no-repaint -----------------------------------------------------------------------------------------------------


def test_identical_history_proves_stability_and_later_days_may_extend_it() -> None:
    inputs = stability_inputs("UDDU", "UDDUUDU")
    evidence = decide(inputs)
    assert (evidence.status, evidence.stability_outcome, evidence.policy_governed) == (
        PROVEN,
        RegimeStabilityOutcome.STABILITY_PROVEN,
        True,
    )
    assert (evidence.earlier_as_of_ns, evidence.later_as_of_ns, evidence.as_of_gap_days) == (
        (D0 + 5) * DAY,
        (D0 + 8) * DAY,
        3,
    )
    assert (evidence.overlap_first_day_index, evidence.overlap_last_day_index, evidence.overlap_day_count) == (
        D0 + 2,
        D0 + 5,
        4,
    )
    assert evidence.repaint_mismatch_day_indices == ()
    earlier_labels, later_labels = rf4t.expected_labels("UDDU"), rf4t.expected_labels("UDDUUDU")
    expected = oracle_tvd(earlier_labels, later_labels)
    assert expected == Fraction(1, 14)  # p = (1/2, 1/2, 0), q = (4/7, 3/7, 0)
    assert (evidence.distribution_drift_exact, evidence.distribution_drift) == ("1/14", rf2t.oracle_half_even(expected))
    assert evidence.distribution == tuple(
        RegimeLabelDistributionEntry(label, left, right)
        for label, left, right in zip(VOCABULARY, oracle_counts(earlier_labels), oracle_counts(later_labels))
    )
    assert (evidence.drift_within_cap, evidence.drift_methodology_id, evidence.reason_codes) == (
        True,
        REGIME_DRIFT_METHODOLOGY_ID,
        (),
    )
    assert (evidence.earlier_label_evidence_digest, evidence.later_label_evidence_digest) == (
        inputs.earlier_labels.label_evidence_digest,
        inputs.later_labels.label_evidence_digest,
    )
    assert evidence.rule_set_digest == REGIME_STABILITY_RULE_SET_DIGEST


def test_exactly_one_changed_historical_day_rejects_stability() -> None:
    evidence = decide(stability_inputs("UDDU", "UUDUUDU"))  # move 2 changed from D to U: label(D0+3) repaints
    expected = [
        D0 + 2 + index
        for index, (left, right) in enumerate(zip(rf4t.expected_labels("UDDU"), rf4t.expected_labels("UUDUUDU")))
        if left != right
    ]
    assert evidence.repaint_mismatch_day_indices == tuple(expected) == (D0 + 3,)
    assert (evidence.status, evidence.stability_outcome, evidence.advances) == (
        REJECTED,
        RegimeStabilityOutcome.STABILITY_REJECTED,
        False,
    )
    assert code("repaint_detected") in evidence.reason_codes


def test_a_label_filled_in_later_is_a_repaint() -> None:
    # The earlier evidence lacks the close of day D0+3 (two UNLABELED days); the later one has it.
    policy = stability_policy(max_unlabeled_fraction=d("1"))
    earlier = rf4t.label_inputs("UDUD", policy=policy, drop_days=(D0 + 3,))
    later = rf4t.label_inputs("UDUDUD", policy=policy)
    inputs = RegimeStabilityInputs(
        "rf5-synthetic-2", "corr-rf5", policy, earlier, rf4t.build(earlier), later, rf4t.build(later)
    )
    evidence = decide(inputs)
    assert evidence.repaint_mismatch_day_indices == (D0 + 4, D0 + 5)
    assert evidence.status is REJECTED


@pytest.mark.parametrize(("earlier_moves", "status"), [("UDD", PROVEN), ("UD", INSUFFICIENT)])
def test_the_overlap_minimum_is_inclusive(earlier_moves: str, status: RegimeStabilityStatus) -> None:
    evidence = decide(stability_inputs(earlier_moves, "UDDUU", policy=stability_policy(distribution_drift_cap=d("1"))))
    assert evidence.overlap_day_count == len(earlier_moves)
    assert evidence.status is status
    if status is INSUFFICIENT:
        assert evidence.stability_outcome is RegimeStabilityOutcome.INSUFFICIENT_OVERLAP
        assert evidence.reason_codes == (code("overlap_below_governed_minimum"),)


@pytest.mark.parametrize(("later_moves", "admitted"), [("UDDUU", True), ("UDDU", False)])
def test_the_as_of_gap_minimum_is_inclusive(later_moves: str, admitted: bool) -> None:
    policy = stability_policy(stability_min_asof_gap_days=2, distribution_drift_cap=d("1"))
    inputs = stability_inputs("UDD", later_moves, policy=policy)
    if admitted:
        assert decide(inputs).as_of_gap_days == 2
    else:
        with refused("as_of_gap_below_governed_minimum"):
            build(inputs)


def test_the_same_or_a_reversed_as_of_pair_is_refused() -> None:
    with refused("as_of_not_strictly_increasing"):
        build(stability_inputs("UDDU", "UDDU"))
    with refused("as_of_not_strictly_increasing"):
        build(stability_inputs("UDDUU", "UDDU"))


# --- drift ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cap", "status"),
    [(d("0.6"), PROVEN), (d("0.5"), PROVEN), (d("0.499999999999999999"), REJECTED)],
)
def test_the_drift_cap_is_inclusive_and_a_matching_overlap_never_bypasses_it(
    cap: str, status: RegimeStabilityStatus
) -> None:
    # The earlier window is all CALM; the later one adds four STRESSED days: p = (1, 0, 0), q = (1/2, 1/2, 0).
    evidence = decide(stability_inputs("UUUU", "UUUUDDDD", policy=stability_policy(distribution_drift_cap=cap)))
    drift = oracle_tvd(rf4t.expected_labels("UUUU"), rf4t.expected_labels("UUUUDDDD"))
    assert drift == Fraction(1, 2)
    assert (evidence.distribution_drift, evidence.distribution_drift_exact) == ("0.500000000000000000", "1/2")
    assert evidence.repaint_mismatch_day_indices == ()  # the overlap matches exactly
    assert evidence.drift_within_cap is (drift <= Fraction(cap))
    assert evidence.status is status
    assert evidence.distribution[1] == RegimeLabelDistributionEntry("STRESSED", 0, 4)  # absent on one side: zero
    if status is REJECTED:
        assert evidence.reason_codes == (code("distribution_drift_above_cap"),)


def test_unlabeled_days_take_part_in_the_distribution() -> None:
    policy = stability_policy(max_unlabeled_fraction=d("1"), distribution_drift_cap=d("1"))
    evidence = decide(stability_inputs("UDUD", "UDUDUDUD", policy=policy, drop_days=(D0 + 3,)))
    earlier = ["CALM", "STRESSED", REGIME_UNLABELED, REGIME_UNLABELED]
    later = [*earlier, "STRESSED", "CALM", "STRESSED", "CALM"]
    assert [entry.label_id for entry in evidence.distribution] == list(VOCABULARY)
    assert evidence.distribution[2] == RegimeLabelDistributionEntry(REGIME_UNLABELED, 2, 2)
    assert evidence.distribution_drift_exact == "1/4" and oracle_tvd(earlier, later) == Fraction(1, 4)
    assert evidence.status is PROVEN


@pytest.mark.parametrize(
    ("earlier", "later"),
    [((4, 0, 0), (4, 4, 0)), ((1, 1, 0), (1, 1, 0)), ((3, 1, 2), (0, 5, 1)), ((0, 0, 7), (7, 0, 0))],
)
def test_the_public_drift_measure_is_the_exact_total_variation_distance(
    earlier: tuple[int, ...], later: tuple[int, ...]
) -> None:
    expected = (
        sum((abs(Fraction(a, sum(earlier)) - Fraction(b, sum(later))) for a, b in zip(earlier, later)), Fraction(0)) / 2
    )
    assert measure_regime_label_distribution_drift(list(earlier), list(later)) == expected


@pytest.mark.parametrize(
    ("earlier", "later"),
    [((), ()), ((1, 0), (1,)), ((0, 0), (1, 1)), ((1, -1), (1, 1)), ((1, True), (1, 1)), ("11", (1, 1))],
)
def test_the_public_drift_measure_refuses_malformed_counts(earlier: object, later: object) -> None:
    with refused("drift_counts_malformed"):
        measure_regime_label_distribution_drift(earlier, later)  # type: ignore[arg-type]


# --- governance, upstream verdicts and provenance -------------------------------------------------------------------


def test_an_ungoverned_policy_never_masquerades_as_proven() -> None:
    policy = rf4t.updown_policy(governed=False)
    evidence = decide(stability_inputs("UDDU", "UDDUU", policy=policy))
    assert (evidence.status, evidence.stability_outcome, evidence.policy_governed, evidence.advances) == (
        NEEDS_GOVERNANCE,
        RegimeStabilityOutcome.STABILITY_PROVEN,
        False,
        False,
    )
    assert evidence.reason_codes == (code("policy_needs_governance_approval"),)
    repainted = decide(stability_inputs("UDDU", "UUDUU", policy=policy))
    assert repainted.status is REJECTED  # a repaint stays a rejection; governance only ever withholds a proof
    assert code("policy_needs_governance_approval") in repainted.reason_codes


def test_a_label_evidence_that_fails_its_unlabeled_cap_rejects_stability() -> None:
    policy = stability_policy(max_unlabeled_fraction=d("0.4"))
    evidence = decide(stability_inputs("UDUD", "UDUDUDUD", policy=policy, drop_days=(D0 + 3,)))
    assert (evidence.earlier_label_verdict, evidence.later_label_verdict) == ("FAIL", "PASS")  # 2/4 then 2/8
    assert (evidence.status, evidence.stability_outcome) == (REJECTED, RegimeStabilityOutcome.STABILITY_PROVEN)
    assert evidence.reason_codes == (code("earlier_label_evidence_failed"),)
    assert evidence.earlier_label_verdict == EdgeGateVerdict.FAIL.value


def test_every_input_is_reproven_and_bound_to_one_policy() -> None:
    inputs = stability_inputs("UDDU", "UDDUU")
    other = stability_policy(distribution_drift_cap=d("0.3"))
    with refused("later_labels_policy_mismatch"):
        build(stability_inputs("UDDU", "UDDUU", later_policy=other))
    earlier_other = rf4t.label_inputs("UDDU", policy=other)
    with refused("earlier_labels_policy_mismatch"):
        build(replace(inputs, earlier_label_inputs=earlier_other, earlier_labels=rf4t.build(earlier_other)))
    forged = replace(inputs.earlier_labels, unlabeled_within_cap=False)
    forged = replace(forged, label_evidence_digest=regime_label_evidence_digest(forged))
    with refused("earlier_labels_not_reconstructed"):
        build(replace(inputs, earlier_labels=forged))
    with refused("later_labels_reconstruction_failed"):
        build(replace(inputs, later_label_inputs=replace(inputs.later_label_inputs, label_evidence_id="")))
    with refused("policy_not_intact"):
        build(replace(inputs, policy=replace(inputs.policy, distribution_drift_cap=d("0.9"))))
    for name, reason in (
        ("policy", "policy_malformed"),
        ("earlier_label_inputs", "earlier_label_inputs_malformed"),
        ("later_labels", "later_labels_malformed"),
    ):
        with refused(reason):
            build(replace(inputs, **{name: None}))
    with refused("stability_evidence_id_invalid"):
        build(replace(inputs, stability_evidence_id=" rf5"))
    with refused("inputs_malformed"):
        build(None)


# --- the verifier ---------------------------------------------------------------------------------------------------


def test_every_field_is_digest_bound_and_reproven() -> None:
    inputs = stability_inputs("UDDU", "UUDUUDU")
    evidence = decide(inputs)
    forged = reseal(evidence, status=PROVEN, advances=True, repaint_mismatch_day_indices=())
    assert {
        code("field_mismatch:status"),
        code("field_mismatch:advances"),
        code("field_mismatch:repaint_mismatch_day_indices"),
    } <= set(verify_regime_stability_evidence(forged, inputs).reason_codes)
    for name, _ in REGIME_NON_CLAIM_FLAGS:
        assert (
            verify_regime_stability_evidence(reseal(evidence, **{name: not getattr(evidence, name)}), inputs).intact
            is False
        )


def test_the_verifier_is_total() -> None:
    inputs = stability_inputs("UDDU", "UDDUU")
    evidence = decide(inputs)
    for value in (
        None,
        {},
        "evidence",
        evidence.distribution[0],
        replace(evidence, status="STABILITY_PROVEN"),
        replace(evidence, overlap_day_count=-1),
        replace(evidence, repaint_mismatch_day_indices=[]),
    ):
        verification = verify_regime_stability_evidence(value, inputs)
        assert verification.intact is False
        assert verification.reason_codes in ((code("evidence_type_invalid"),), (code("evidence_serialization_failed"),))
    assert verify_regime_stability_evidence(evidence, None).reason_codes == (code("evidence_reconstruction_failed"),)  # type: ignore[arg-type]


# --- static discipline, rule set and API ----------------------------------------------------------------------------


def test_the_module_is_pure_and_never_imports_the_runtime_regime_package() -> None:
    pit.assert_module_is_pure(
        stability_module,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.regime_feature_policy",
            "crypto_core.validation.regime_label_evidence",
        },
    )
    assert "crypto_core.regime." not in SOURCE and "from crypto_core.regime" not in SOURCE


def test_labels_are_compared_exactly_with_no_tolerance() -> None:
    tree = ast.parse(SOURCE)
    (function,) = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "build_regime_stability_evidence"
    ]
    source = ast.unparse(function)
    assert "tuple((day for day in overlap if earlier_by_day[day] != later_by_day[day]))" in source
    assert "within = drift <= cap" in source


def test_execution_capital_and_scheduler_names_are_only_structural_false_flags() -> None:
    flags = dict(REGIME_NON_CLAIM_FLAGS)
    names = {node.id for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, ast.Attribute)}
    risky = {
        name
        for name in names
        if re.search(r"(^|_)(live|orders?|capital|scheduler|connector|shadow|execution)(_|$)", name)
    }
    assert risky <= set(flags)
    assert {item.name: item.default for item in fields(RegimeStabilityEvidence) if item.name in flags} == flags
    assert all(
        item.default is dataclasses.MISSING for item in fields(RegimeStabilityEvidence) if item.name not in flags
    )
    assert all(item.default is dataclasses.MISSING for item in fields(RegimeStabilityInputs))
    assert (flags["regime_filter_admitted"], flags["regime_conditioned_performance_proven"]) == (False, False)


def test_the_rule_set_commits_the_controller_methodology_and_is_handed_out_fresh() -> None:
    rule_set = regime_stability_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == REGIME_STABILITY_RULE_SET_DIGEST
    assert rule_set["drift_methodology_id"] == "RF5_TOTAL_VARIATION_LABEL_DISTRIBUTION_DRIFT_V1"
    assert rule_set["advance_rule_id"] == "only_stability_proven_advances.v1"
    rule_set["drift_methodology_id"] = "other"
    assert regime_stability_rule_set()["drift_methodology_id"] == REGIME_DRIFT_METHODOLOGY_ID


def test_the_public_api_is_exact() -> None:
    assert set(stability_module.__all__) == {
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
    }
