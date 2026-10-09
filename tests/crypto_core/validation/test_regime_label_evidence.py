"""Tests for the RF-4 prior-day-close regime label evidence (``regime_label_evidence``).

Fixtures: the authentic EF-3 manifest, authenticated ``HistoricalPitDataset`` and governed synthetic RF-2 policies of
the RF-2/RF-3 test modules, over "up/down" close worlds (one authenticated record per daily close). With the one-feature policy below, ``label(D)`` is ``STRESSED`` exactly when day ``D - 1``
closed below day ``D - 2`` (a positive two-day peak distance) and ``CALM`` otherwise, so every expected label is
derived here from the move string alone, never from the module. Every value is a SYNTHETIC TEST VALUE.
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

import crypto_core.validation.regime_label_evidence as label_module
from crypto_core.validation.edge_artifact_core import EdgeGateVerdict, edge_canonical_json, edge_sha256_text
from crypto_core.validation.historical_pit_dataset import HistoricalPitRecord
from crypto_core.validation.regime_feature_policy import (
    REGIME_NON_CLAIM_FLAGS,
    REGIME_UNLABELED,
    RegimeFeatureClass,
    RegimeFeaturePolicy,
    RegimePredicateOperator,
)
from crypto_core.validation.regime_feature_series_evidence import regime_feature_series_evidence_digest
from crypto_core.validation.regime_label_evidence import (
    REGIME_LABEL_RULE_SET_DIGEST,
    RegimeDayLabel,
    RegimeLabelCount,
    RegimeLabelEvidence,
    RegimeLabelEvidenceError,
    RegimeLabelInputs,
    build_regime_label_evidence,
    regime_label_evidence_digest,
    regime_label_evidence_to_dict,
    regime_label_rule_set,
    verify_regime_label_evidence,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

try:  # the module objects pytest collects (basename import), so cached fixtures are shared with their own tests
    import test_regime_feature_policy as rf2t
    import test_regime_feature_series_evidence as rf3t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_regime_feature_policy as rf2t
    from tests.crypto_core.validation import test_regime_feature_series_evidence as rf3t

_PREFIX = "regime_label_evidence"
SOURCE = Path(label_module.__file__).read_text(encoding="utf-8")
DAY, D0 = rf3t.DAY, rf3t.D0
F2 = RegimeFeatureClass.F2_DRAWDOWN_STATE
LT, LTE, GT, GTE = (RegimePredicateOperator(name) for name in ("LT", "LTE", "GT", "GTE"))
DD = rf2t.DD
UNIT = Fraction(1, 10**18)
d = rf2t.d


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def refused(text: str):
    """``pytest.raises`` for one exact RF-4 construction error."""

    return pytest.raises(RegimeLabelEvidenceError, match=f"^{re.escape(code(text))}$")


def updown_policy(
    *, governed: bool = True, rules: object = None, label_set: object = ("CALM", "STRESSED"), **overrides: object
) -> RegimeFeaturePolicy:
    """One F2 feature over two closes: STRESSED on any drop, CALM otherwise (SYNTHETIC rules)."""

    args: dict[str, object] = {
        "features": [rf2t.feature(DD, F2, lookback=2)],
        "label_set": list(label_set),  # type: ignore[call-overload]
        "label_rules": rules
        if rules is not None
        else [
            rf2t.rule(1, "STRESSED", rf2t.predicate(DD, GT, d("0"))),
            rf2t.rule(2, "CALM", rf2t.predicate(DD, LTE, d("0"))),
        ],
        **overrides,
    }
    return rf2t.governed(**args) if governed else rf2t.build(**args)


def moves_closes(moves: str) -> tuple[str, ...]:
    """Closes of days D0, D0+1, ...: 100, then one move per later day (U up one, D down one, F flat)."""

    value, closes = 100, ["100"]
    for move in moves:
        value += {"U": 1, "D": -1, "F": 0}[move]
        closes.append(str(value))
    return tuple(closes)


def expected_labels(moves: str) -> list[str]:
    """The oracle: label(D0 + 2 + i) is STRESSED iff move i (day D0+1+i against D0+i) is a drop."""

    return ["STRESSED" if move == "D" else "CALM" for move in moves]


def label_inputs(
    moves: str,
    *,
    policy: RegimeFeaturePolicy | None = None,
    drop_days: tuple[int, ...] = (),
    closes: tuple[str, ...] | None = None,
    records: Sequence[HistoricalPitRecord] | None = None,
    **overrides: object,
) -> RegimeLabelInputs:
    """Labels for days D0+2 .. D0+1+len(moves), as of the start of the last day, over an authenticated dataset of one
    record per close; ``drop_days`` removes records and ``records`` replaces them all."""

    closes = moves_closes(moves) if closes is None else closes
    series_inputs = rf3t.series_inputs(
        policy=updown_policy() if policy is None else policy,
        records=rf3t.pit_records(closes, skip=drop_days) if records is None else records,
        last=D0 + len(closes),
        first_feature_day=D0 + 2,
    )
    values: dict[str, object] = {
        "label_evidence_id": "rf4-synthetic-1",
        "correlation_id": "corr-rf4",
        "policy": series_inputs.policy,
        "feature_series_inputs": series_inputs,
        "feature_series": rf3t.build(series_inputs),
    }
    values.update(overrides)
    return RegimeLabelInputs(**values)  # type: ignore[arg-type]


def build(inputs: object) -> RegimeLabelEvidence:
    return build_regime_label_evidence(inputs)  # type: ignore[arg-type]


def decide(inputs: RegimeLabelInputs) -> RegimeLabelEvidence:
    """Build, then re-prove by reconstruction: every evidence a test reads is intact."""

    evidence = build(inputs)
    verification = verify_regime_label_evidence(evidence, inputs)
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert verification.recomputed_digest == evidence.label_evidence_digest
    assert json.loads(verification.canonical_json) == regime_label_evidence_to_dict(evidence)
    assert {name: getattr(evidence, name) for name, _ in REGIME_NON_CLAIM_FLAGS} == dict(REGIME_NON_CLAIM_FLAGS)
    return evidence


def reseal(evidence: RegimeLabelEvidence, **changes: object) -> RegimeLabelEvidence:
    changed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(changed, label_evidence_digest=regime_label_evidence_digest(changed))


def labels_of(evidence: RegimeLabelEvidence) -> list[str]:
    return [item.label_id for item in evidence.labels]


# --- the labels -----------------------------------------------------------------------------------------------------


def test_labels_follow_the_prior_day_close_and_cover_every_day_once() -> None:
    moves = "UDDUFDUU"
    inputs = label_inputs(moves)
    evidence = decide(inputs)
    series, policy = inputs.feature_series, inputs.policy
    assert labels_of(evidence) == expected_labels(moves)
    assert [item.day_index for item in evidence.labels] == list(range(D0 + 2, D0 + 2 + len(moves)))
    assert [item.matched_rule_priority for item in evidence.labels] == [1 if move == "D" else 2 for move in moves]
    assert all(item.unlabeled_reason_codes == () for item in evidence.labels)
    assert (evidence.gate_verdict, evidence.advances, evidence.policy_governed) == (EdgeGateVerdict.PASS, True, True)
    assert (evidence.regime_feature_policy_digest, evidence.feature_series_digest, evidence.as_of_ns) == (
        policy.regime_feature_policy_digest,
        series.feature_series_digest,
        series.as_of_ns,
    )
    assert (evidence.first_label_day_index, evidence.last_label_day_index, evidence.label_day_count) == (
        D0 + 2,
        D0 + 1 + len(moves),
        len(moves),
    )
    assert evidence.label_counts == (
        RegimeLabelCount("CALM", moves.count("U") + moves.count("F")),
        RegimeLabelCount("STRESSED", moves.count("D")),
        RegimeLabelCount(REGIME_UNLABELED, 0),
    )
    assert (evidence.unlabeled_day_count, evidence.unlabeled_fraction, evidence.unlabeled_within_cap) == (
        0,
        "0/1",
        True,
    )
    assert (evidence.rule_set_digest, evidence.verdict_reason_codes) == (REGIME_LABEL_RULE_SET_DIGEST, ())
    assert build(inputs) == evidence  # deterministic


def test_a_label_never_reads_its_own_day_or_a_later_one() -> None:
    moves = "UUDUU"
    base = decide(label_inputs(moves))
    # Day D0+4's close drops; label(D0+4) reads only D0+2 and D0+3, so only label(D0+5) may change.
    closes = list(moves_closes(moves))
    closes[4] = "50"
    changed = decide(label_inputs(moves, closes=tuple(closes)))
    assert changed.labels[:3] == base.labels[:3]
    assert (base.labels[3].label_id, changed.labels[3].label_id) == ("CALM", "STRESSED")


@pytest.mark.parametrize("operator", [LT, LTE, GT, GTE])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_every_operator_boundary_matches_an_exact_comparison(operator: RegimePredicateOperator, offset: int) -> None:
    value = Fraction(1, 10)  # closes 100 -> 90 measure exactly 0.1 on day D0+2
    threshold = value + offset * UNIT
    policy = updown_policy(
        label_set=("HIT",),
        rules=[rf2t.rule(1, "HIT", rf2t.predicate(DD, operator, rf2t.oracle_half_even(threshold)))],
        max_unlabeled_fraction=d("1"),
    )
    evidence = decide(label_inputs("", policy=policy, closes=("100", "90")))
    expected = {LT: value < threshold, LTE: value <= threshold, GT: value > threshold, GTE: value >= threshold}[
        operator
    ]
    assert labels_of(evidence) == (["HIT"] if expected else [REGIME_UNLABELED])
    if not expected:
        assert evidence.labels[0].unlabeled_reason_codes == (code("no_rule_matched"),)


def test_the_first_matching_rule_wins_in_ascending_priority() -> None:
    def labelled(first: str, second: str) -> list[str]:
        rules = [
            rf2t.rule(1, first, rf2t.predicate(DD, GTE, d("0") if first == "A" else d("0.05"))),
            rf2t.rule(2, second, rf2t.predicate(DD, GTE, d("0.05") if first == "A" else d("0"))),
        ]
        policy = updown_policy(label_set=("A", "B"), rules=rules)
        return labels_of(decide(label_inputs("", policy=policy, closes=("100", "90"))))

    assert labelled("A", "B") == ["A"]  # both rules hold for 0.1: priority 1 decides
    assert labelled("B", "A") == ["B"]


def test_no_matching_rule_is_unlabeled_and_counted() -> None:
    policy = updown_policy(
        label_set=("STRESSED",),
        rules=[rf2t.rule(1, "STRESSED", rf2t.predicate(DD, GT, d("0.5")))],
        max_unlabeled_fraction=d("1"),
    )
    evidence = decide(label_inputs("DDU", policy=policy))
    assert labels_of(evidence) == [REGIME_UNLABELED] * 3
    assert all(item.unlabeled_reason_codes == (code("no_rule_matched"),) for item in evidence.labels)
    assert evidence.label_counts == (RegimeLabelCount("STRESSED", 0), RegimeLabelCount(REGIME_UNLABELED, 3))
    assert (evidence.unlabeled_fraction, evidence.gate_verdict) == ("1/1", EdgeGateVerdict.PASS)


def test_one_missing_required_feature_makes_the_day_unlabeled_never_filled() -> None:
    # The two-feature RF-2 test policy over the RF-3 world without the record of day D0+5.
    series_inputs = rf3t.series_inputs(records=rf3t.pit_records(skip=(D0 + 5,)))
    inputs = RegimeLabelInputs(
        "rf4-synthetic-2", "corr-rf4", series_inputs.policy, series_inputs, rf3t.build(series_inputs)
    )
    evidence = decide(inputs)
    by_day = {item.day_index: item for item in evidence.labels}
    both = (code(f"required_feature_unavailable:{DD}"), code(f"required_feature_unavailable:{rf2t.VOL}"))
    assert by_day[D0 + 6].unlabeled_reason_codes == both
    assert by_day[D0 + 7].unlabeled_reason_codes == both
    assert by_day[D0 + 8].unlabeled_reason_codes == (code(f"required_feature_unavailable:{rf2t.VOL}"),)
    assert {day for day, item in by_day.items() if item.label_id == REGIME_UNLABELED} >= {D0 + 6, D0 + 7, D0 + 8}
    assert evidence.label_day_count == 8 and len(evidence.labels) == 8  # no day dropped


@pytest.mark.parametrize(
    ("cap", "verdict"),
    [
        (d("0.3"), EdgeGateVerdict.PASS),
        (d("0.25"), EdgeGateVerdict.PASS),
        (d("0.249999999999999999"), EdgeGateVerdict.FAIL),
    ],
)
def test_the_unlabeled_cap_is_inclusive_and_every_day_stays_in_the_denominator(
    cap: str, verdict: EdgeGateVerdict
) -> None:
    moves = "UDUDUDUD"
    evidence = decide(label_inputs(moves, policy=updown_policy(max_unlabeled_fraction=cap), drop_days=(D0 + 3,)))
    unlabeled_days = [item.day_index for item in evidence.labels if item.label_id == REGIME_UNLABELED]
    assert unlabeled_days == [D0 + 4, D0 + 5]  # the two days whose two-close windows read day D0+3
    fraction = Fraction(len(unlabeled_days), len(moves))
    assert fraction == Fraction(1, 4)
    assert (evidence.unlabeled_day_count, evidence.label_day_count, evidence.unlabeled_fraction) == (2, 8, "1/4")
    assert evidence.gate_verdict is verdict and evidence.advances is (verdict is EdgeGateVerdict.PASS)
    assert evidence.unlabeled_within_cap is (fraction <= Fraction(cap))
    if verdict is EdgeGateVerdict.FAIL:
        assert evidence.verdict_reason_codes == (code("unlabeled_fraction_above_cap"),)


def test_a_policy_without_human_governance_never_advances_and_a_cap_breach_still_fails() -> None:
    ungoverned = decide(label_inputs("UDU", policy=updown_policy(governed=False)))
    assert (ungoverned.gate_verdict, ungoverned.advances, ungoverned.policy_governed) == (
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        False,
        False,
    )
    assert ungoverned.verdict_reason_codes == (code("policy_needs_governance_approval"),)
    breached = decide(
        label_inputs("UDUD", policy=updown_policy(governed=False, max_unlabeled_fraction=d("0")), drop_days=(D0 + 3,))
    )
    assert breached.gate_verdict is EdgeGateVerdict.FAIL
    assert breached.verdict_reason_codes == (
        code("policy_needs_governance_approval"),
        code("unlabeled_fraction_above_cap"),
    )


# --- provenance -----------------------------------------------------------------------------------------------------


def test_every_input_is_reproven_and_bound_to_one_policy() -> None:
    inputs = label_inputs("UDU")
    series = inputs.feature_series
    forged_record = replace(series.records[0], value=d("0.2"))
    forged = replace(series, records=(forged_record, *series.records[1:]))
    forged = replace(forged, feature_series_digest=regime_feature_series_evidence_digest(forged))
    with refused("feature_series_not_reconstructed"):
        build(replace(inputs, feature_series=forged))
    with refused("feature_series_reconstruction_failed"):
        build(replace(inputs, feature_series_inputs=replace(inputs.feature_series_inputs, as_of_ns=1)))
    other_policy = updown_policy(max_unlabeled_fraction=d("0.4"))
    with refused("feature_series_policy_mismatch"):
        build(replace(inputs, policy=other_policy))
    with refused("policy_not_intact"):
        build(replace(inputs, policy=replace(inputs.policy, max_unlabeled_fraction=d("0.9"))))
    for name, reason in (
        ("policy", "policy_malformed"),
        ("feature_series_inputs", "feature_series_inputs_malformed"),
        ("feature_series", "feature_series_malformed"),
    ):
        with refused(reason):
            build(replace(inputs, **{name: None}))
    with refused("label_evidence_id_invalid"):
        build(replace(inputs, label_evidence_id=""))
    with refused("inputs_malformed"):
        build(None)


def test_every_field_is_digest_bound_and_reproven() -> None:
    inputs = label_inputs("UDDU")
    evidence = decide(inputs)
    forged = reseal(evidence, label_counts=(RegimeLabelCount("CALM", 3), *evidence.label_counts[1:]))
    assert set(verify_regime_label_evidence(forged, inputs).reason_codes) == {
        code("field_mismatch:label_counts"),
        code("field_mismatch:label_evidence_digest"),
    }
    relabelled = reseal(evidence, labels=(RegimeDayLabel(D0 + 2, "STRESSED", 1, ()), *evidence.labels[1:]))
    assert code("field_mismatch:labels") in verify_regime_label_evidence(relabelled, inputs).reason_codes
    for name, _ in REGIME_NON_CLAIM_FLAGS:
        assert (
            verify_regime_label_evidence(reseal(evidence, **{name: not getattr(evidence, name)}), inputs).intact
            is False
        )


def test_the_verifier_is_total() -> None:
    inputs = label_inputs("UD")
    evidence = decide(inputs)
    for value in (
        None,
        {},
        "evidence",
        evidence.labels[0],
        replace(evidence, gate_verdict="PASS"),
        replace(evidence, label_day_count=-1),
        replace(evidence, labels=list(evidence.labels)),
    ):
        verification = verify_regime_label_evidence(value, inputs)
        assert verification.intact is False
        assert verification.reason_codes in ((code("evidence_type_invalid"),), (code("evidence_serialization_failed"),))
    assert verify_regime_label_evidence(evidence, None).reason_codes == (code("evidence_reconstruction_failed"),)  # type: ignore[arg-type]


# --- static discipline, rule set and API ----------------------------------------------------------------------------


def test_the_module_is_pure_and_never_imports_the_runtime_regime_package() -> None:
    pit.assert_module_is_pure(
        label_module,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.regime_feature_policy",
            "crypto_core.validation.regime_feature_series_evidence",
        },
    )
    assert "crypto_core.regime." not in SOURCE and "from crypto_core.regime" not in SOURCE


def test_labels_read_only_the_records_of_their_own_day() -> None:
    tree = ast.parse(SOURCE)
    (function,) = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_day_label"]
    lookups = [
        ast.unparse(node)
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "records.get"
    ]
    assert lookups == ["records.get((feature.feature_id, day))"]


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
    assert {item.name: item.default for item in fields(RegimeLabelEvidence) if item.name in flags} == flags
    assert all(item.default is dataclasses.MISSING for item in fields(RegimeLabelEvidence) if item.name not in flags)
    assert all(item.default is dataclasses.MISSING for item in fields(RegimeLabelInputs))


def test_the_rule_set_commits_the_controller_methodology_and_is_handed_out_fresh() -> None:
    rule_set = regime_label_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == REGIME_LABEL_RULE_SET_DIGEST
    assert rule_set["unlabeled_label_id"] == REGIME_UNLABELED
    assert "first_rule_whose_conjunctive_predicates_all_hold_wins" in str(rule_set["rule_evaluation_id"])
    rule_set["unlabeled_label_id"] = "OTHER"
    assert regime_label_rule_set()["unlabeled_label_id"] == REGIME_UNLABELED


def test_the_public_api_is_exact() -> None:
    assert set(label_module.__all__) == {
        "REGIME_LABEL_NON_CLAIM_FLAGS",
        "REGIME_LABEL_RULE_SET_DIGEST",
        "RegimeDayLabel",
        "RegimeLabelCount",
        "RegimeLabelEvidence",
        "RegimeLabelEvidenceError",
        "RegimeLabelInputs",
        "build_regime_label_evidence",
        "regime_label_evidence_digest",
        "regime_label_evidence_to_dict",
        "regime_label_rule_set",
        "verify_regime_label_evidence",
    }
