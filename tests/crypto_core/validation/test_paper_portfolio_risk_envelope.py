"""RG-2 paper portfolio risk envelope tests (RG2_PAPER_PORTFOLIO_RISK_ENVELOPE_V1).

SYNTHETIC TEST VALUES ONLY. Every governed number, identifier and approval in this file is a synthetic test value chosen
to exercise structure. None is a production threshold and none is production-approved. The ``HUMAN_GOVERNANCE``
approvals built here are synthetic test fixtures that exercise the PASS branch; ``TEST_ONLY_SYNTHETIC`` approvals
exercise the synthetic-approval refusal.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import re
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.paper_portfolio_risk_envelope as envelope_module
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PAPER_PORTFOLIO_RISK_ENVELOPE_NON_CLAIM_FLAGS,
    PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST,
    PaperPortfolioCorrelationCap,
    PaperPortfolioMarketCap,
    PaperPortfolioRiskEnvelope,
    PaperPortfolioRiskEnvelopeApproval,
    PaperPortfolioRiskEnvelopeApprovalKind,
    PaperPortfolioRiskEnvelopeError,
    PaperPortfolioSleeveCap,
    PaperPortfolioStopLevel,
    PaperSleeveLadderBoundary,
    PaperSleeveLadderTier,
    build_paper_portfolio_risk_envelope,
    paper_portfolio_risk_envelope_digest,
    paper_portfolio_risk_envelope_from_payload,
    paper_portfolio_risk_envelope_payload_is_well_formed,
    paper_portfolio_risk_envelope_rule_set,
    paper_portfolio_risk_envelope_to_dict,
    verify_paper_portfolio_risk_envelope,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

_PREFIX = "paper_portfolio_risk_envelope"
INT64_MAX = 9223372036854775807
PROBATION = PaperSleeveLadderTier.PROBATION
STANDARD = PaperSleeveLadderTier.STANDARD
EXPANDED = PaperSleeveLadderTier.EXPANDED
HUMAN = PaperPortfolioRiskEnvelopeApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = PaperPortfolioRiskEnvelopeApprovalKind.TEST_ONLY_SYNTHETIC
# The approval, the verdict it yields and the two digests are outside the governed policy (the module's contract).
_NON_POLICY_FIELDS = frozenset(
    {
        "gate_verdict",
        "advances",
        "policy_digest",
        "approval",
        "synthetic_test_approval_used",
        "verdict_reason_codes",
        "envelope_digest",
    }
)


class _Text(str):
    """A ``str`` subclass, refused wherever exact text is required."""


class _Int(int):
    """An ``int`` subclass, refused wherever an exact native integer is required."""


class _List(list):
    """A ``list`` subclass, refused wherever an exact caller sequence is required."""


@dataclass(frozen=True)
class _SleeveCapSubclass(PaperPortfolioSleeveCap):
    """A record subclass, refused wherever the exact record type is required."""


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _raises(code: str):
    """``pytest.raises`` for one exact prefixed construction-error code."""

    return pytest.raises(PaperPortfolioRiskEnvelopeError, match=re.escape(_code(code)))


def d(text: str) -> str:
    """A SYNTHETIC TEST VALUE rendered as canonical scale-18 decimal text."""

    negative = text.startswith("-")
    integer, _, fraction = text.lstrip("-").partition(".")
    rendered = f"{integer}.{fraction.ljust(18, '0')}"
    return f"-{rendered}" if negative else rendered


def sleeve(sleeve_id: str, cap: str) -> PaperPortfolioSleeveCap:
    return PaperPortfolioSleeveCap(sleeve_id=sleeve_id, max_paper_risk_budget=d(cap))


def market(market_symbol: str, cap: str) -> PaperPortfolioMarketCap:
    return PaperPortfolioMarketCap(market_symbol=market_symbol, max_paper_risk_budget=d(cap))


def stop(level: object, threshold: str) -> PaperPortfolioStopLevel:
    return PaperPortfolioStopLevel(
        stop_level=level,  # type: ignore[arg-type]
        max_portfolio_drawdown_fraction=d(threshold),
    )


def correlation(cap: str = "0.6", lookback: object = 60, overlap: object = 30) -> PaperPortfolioCorrelationCap:
    return PaperPortfolioCorrelationCap(
        max_pairwise_correlation=d(cap),
        lookback_window_days=lookback,  # type: ignore[arg-type]
        min_overlap_days=overlap,  # type: ignore[arg-type]
    )


def boundary(
    lower: object,
    upper: object,
    *,
    probation: object = 30,
    promotion_sharpe: str = "1",
    promotion_drawdown: str = "0.1",
    demotion_sharpe: str = "0",
    demotion_drawdown: str = "0.2",
) -> PaperSleeveLadderBoundary:
    return PaperSleeveLadderBoundary(
        lower_tier=lower,  # type: ignore[arg-type]
        upper_tier=upper,  # type: ignore[arg-type]
        min_probation_days=probation,  # type: ignore[arg-type]
        promotion_min_paper_sharpe=d(promotion_sharpe),
        promotion_max_drawdown_fraction=d(promotion_drawdown),
        demotion_min_paper_sharpe=d(demotion_sharpe),
        demotion_max_drawdown_fraction=d(demotion_drawdown),
    )


def lower_boundary(**overrides: object) -> PaperSleeveLadderBoundary:
    values: dict[str, object] = {
        "probation": 30,
        "promotion_sharpe": "1",
        "promotion_drawdown": "0.1",
        "demotion_sharpe": "0",
        "demotion_drawdown": "0.2",
    }
    values.update(overrides)
    return boundary(PROBATION, STANDARD, **values)  # type: ignore[arg-type]


def upper_boundary(**overrides: object) -> PaperSleeveLadderBoundary:
    values: dict[str, object] = {
        "probation": 60,
        "promotion_sharpe": "1.5",
        "promotion_drawdown": "0.08",
        "demotion_sharpe": "0.5",
        "demotion_drawdown": "0.15",
    }
    values.update(overrides)
    return boundary(STANDARD, EXPANDED, **values)  # type: ignore[arg-type]


def envelope_args(**overrides: object) -> dict[str, object]:
    """SYNTHETIC TEST VALUES for every governed input; no default exists in the module itself."""

    args: dict[str, object] = {
        "envelope_id": "rg2-synthetic-envelope",
        "envelope_version": "synthetic-v1",
        "total_paper_risk_budget": d("1000"),
        "sleeve_caps": [sleeve("sleeve-alpha", "400"), sleeve("sleeve-beta", "250")],
        "market_caps": [market("BTC-PERPETUAL", "600"), market("ETH-PERPETUAL", "500")],
        "max_sleeve_count": 3,
        "correlation_cap": correlation(),
        "ladder_boundaries": [lower_boundary(), upper_boundary()],
        "portfolio_stop_levels": [stop(1, "0.05"), stop(2, "0.1"), stop(3, "0.15")],
        "approval": None,
    }
    args.update(overrides)
    return args


def build(**overrides: object) -> PaperPortfolioRiskEnvelope:
    return build_paper_portfolio_risk_envelope(**envelope_args(**overrides))  # type: ignore[arg-type]


def approval_for(
    envelope: PaperPortfolioRiskEnvelope, *, kind: object = HUMAN, **overrides: object
) -> PaperPortfolioRiskEnvelopeApproval:
    """A synthetic test approval committing exactly to ``envelope`` unless overridden."""

    values: dict[str, object] = {
        "approval_reference": "synthetic-test-approval-record",
        "approval_digest": "a" * 64,
        "approval_kind": kind,
        "approved_envelope_id": envelope.envelope_id,
        "approved_envelope_version": envelope.envelope_version,
        "approved_policy_digest": envelope.policy_digest,
        "approved_rule_set_digest": envelope.rule_set_digest,
    }
    values.update(overrides)
    return PaperPortfolioRiskEnvelopeApproval(**values)  # type: ignore[arg-type]


def governed(**overrides: object) -> PaperPortfolioRiskEnvelope:
    """An envelope under an exact synthetic HUMAN_GOVERNANCE test approval (PASS-branch fixture only)."""

    return build(approval=approval_for(build(**overrides)), **overrides)


def to_dict(envelope: PaperPortfolioRiskEnvelope) -> dict[str, object]:
    return paper_portfolio_risk_envelope_to_dict(envelope)


def verify(envelope: object) -> EdgeEvidenceVerification:
    return verify_paper_portfolio_risk_envelope(envelope)


def _policy_digest_of(payload: dict[str, object]) -> str:
    return edge_sha256_text(
        edge_canonical_json({name: value for name, value in payload.items() if name not in _NON_POLICY_FIELDS})
    )


def _reseal(envelope: PaperPortfolioRiskEnvelope, **changes: object) -> PaperPortfolioRiskEnvelope:
    changed = replace(envelope, **changes)
    return replace(changed, envelope_digest=paper_portfolio_risk_envelope_digest(changed))


def _corrupted(**changes: object) -> PaperPortfolioRiskEnvelope:
    copy = replace(governed())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


def _assert_intact(envelope: PaperPortfolioRiskEnvelope) -> None:
    verification = verify(envelope)
    assert verification.intact is True, verification.reason_codes
    assert verification.reason_codes == ()
    assert verification.recomputed_digest == envelope.envelope_digest
    assert paper_portfolio_risk_envelope_from_payload(json.loads(verification.canonical_json)) == envelope


# --- A. governance and advancement ------------------------------------------------------------------------------------


def test_unapproved_envelope_is_valid_structure_that_needs_governance_approval() -> None:
    envelope = build()
    assert envelope.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert envelope.advances is False
    assert envelope.approval is None
    assert envelope.synthetic_test_approval_used is False
    assert envelope.verdict_reason_codes == (_code("governance_approval_missing"),)
    _assert_intact(envelope)


def test_exact_human_governance_approval_passes_and_advances() -> None:
    unapproved = build()
    envelope = build(approval=approval_for(unapproved))
    assert envelope.gate_verdict is EdgeGateVerdict.PASS
    assert envelope.advances is True
    assert envelope.verdict_reason_codes == ()
    assert envelope.synthetic_test_approval_used is False
    assert envelope.approval == approval_for(unapproved)
    # The approval governs the policy without being part of it, but it is part of the anchored envelope.
    assert envelope.policy_digest == unapproved.policy_digest
    assert envelope.envelope_digest != unapproved.envelope_digest
    _assert_intact(envelope)


def test_approval_for_a_different_envelope_policy_never_advances() -> None:
    other = build(total_paper_risk_budget=d("2000"))
    envelope = build(approval=approval_for(other))
    assert other.policy_digest != build().policy_digest
    assert envelope.advances is False
    assert envelope.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert envelope.verdict_reason_codes == (_code("governance_approval_policy_digest_mismatch"),)
    _assert_intact(envelope)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("approved_envelope_id", "another-envelope"),
        ("approved_envelope_version", "synthetic-v2"),
        ("approved_policy_digest", "b" * 64),
        ("approved_rule_set_digest", "c" * 64),
    ],
)
def test_every_approval_commitment_must_match_exactly(field_name: str, value: str) -> None:
    envelope = build(approval=approval_for(build(), **{field_name: value}))
    assert envelope.advances is False
    assert envelope.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert envelope.verdict_reason_codes == (_code(f"governance_approval_{field_name[len('approved_') :]}_mismatch"),)
    _assert_intact(envelope)


_GOVERNED_CHANGES: list[dict[str, object]] = [
    {"total_paper_risk_budget": d("1000.5")},
    {"sleeve_caps": [sleeve("sleeve-alpha", "401"), sleeve("sleeve-beta", "250")]},
    {"sleeve_caps": [sleeve("sleeve-alpha", "400")]},
    {"sleeve_caps": [sleeve("sleeve-alpha", "400"), sleeve("sleeve-delta", "250")]},
    {"market_caps": [market("BTC-PERPETUAL", "600"), market("ETH-PERPETUAL", "499")]},
    {"market_caps": [market("BTC-PERPETUAL", "600"), market("ETH-PERPETUAL", "500"), market("SOL-PERPETUAL", "1")]},
    {"max_sleeve_count": 4},
    {"correlation_cap": correlation(cap="0.5")},
    {"correlation_cap": correlation(lookback=61)},
    {"correlation_cap": correlation(overlap=31)},
    {"ladder_boundaries": [lower_boundary(probation=31), upper_boundary()]},
    {"ladder_boundaries": [lower_boundary(promotion_sharpe="1.1"), upper_boundary()]},
    {"ladder_boundaries": [lower_boundary(demotion_sharpe="-0.1"), upper_boundary()]},
    {"ladder_boundaries": [lower_boundary(), upper_boundary(promotion_drawdown="0.07")]},
    {"ladder_boundaries": [lower_boundary(), upper_boundary(demotion_drawdown="0.16")]},
    {"portfolio_stop_levels": [stop(1, "0.05"), stop(2, "0.1"), stop(3, "0.16")]},
    {"portfolio_stop_levels": [stop(1, "0.05"), stop(2, "0.1")]},
]


@pytest.mark.parametrize("change", _GOVERNED_CHANGES, ids=lambda change: next(iter(change)))
def test_any_governed_value_change_makes_an_earlier_approval_stale(change: dict[str, object]) -> None:
    approved = governed()
    changed = build(approval=approved.approval, **change)
    assert changed.policy_digest != approved.policy_digest
    assert changed.envelope_digest != approved.envelope_digest
    assert changed.advances is False
    assert changed.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert changed.verdict_reason_codes == (_code("governance_approval_policy_digest_mismatch"),)
    _assert_intact(changed)


def test_identity_change_makes_an_earlier_approval_stale() -> None:
    approved = governed()
    changed = build(approval=approved.approval, envelope_version="synthetic-v2")
    assert changed.advances is False
    assert changed.verdict_reason_codes == (
        _code("governance_approval_envelope_version_mismatch"),
        _code("governance_approval_policy_digest_mismatch"),
    )


def test_test_only_synthetic_approval_binds_exactly_but_never_advances() -> None:
    envelope = build(approval=approval_for(build(), kind=SYNTHETIC))
    assert envelope.synthetic_test_approval_used is True
    assert envelope.advances is False
    assert envelope.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert envelope.verdict_reason_codes == (_code("governance_approval_test_only_synthetic"),)
    _assert_intact(envelope)


def test_synthetic_approval_with_a_mismatch_reports_both_reasons() -> None:
    envelope = build(approval=approval_for(build(), kind=SYNTHETIC, approved_policy_digest="d" * 64))
    assert envelope.verdict_reason_codes == (
        _code("governance_approval_policy_digest_mismatch"),
        _code("governance_approval_test_only_synthetic"),
    )
    assert envelope.synthetic_test_approval_used is True


def test_approval_kind_text_is_canonicalized_to_the_exact_member() -> None:
    envelope = build(approval=approval_for(build(), kind="HUMAN_GOVERNANCE"))
    assert envelope.approval is not None
    assert type(envelope.approval.approval_kind) is PaperPortfolioRiskEnvelopeApprovalKind
    assert envelope.advances is True
    _assert_intact(envelope)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"approval_reference": ""}, "governance_approval_reference_invalid"),
        ({"approval_reference": " padded"}, "governance_approval_reference_invalid"),
        ({"approval_reference": "line\nbreak"}, "governance_approval_reference_invalid"),
        ({"approval_reference": _Text("subclass")}, "governance_approval_reference_invalid"),
        ({"approval_reference": "x" * 257}, "governance_approval_reference_invalid"),
        ({"approval_reference": "approved-by-live-desk"}, "forbidden_scope_token:governance_approval_reference"),
        ({"approval_digest": "A" * 64}, "governance_approval_digest_invalid"),
        ({"approval_digest": "a" * 63}, "governance_approval_digest_invalid"),
        ({"approval_digest": None}, "governance_approval_digest_invalid"),
        ({"approval_kind": "HUMAN"}, "governance_approval_kind_invalid"),
        ({"approval_kind": _Text("HUMAN_GOVERNANCE")}, "governance_approval_kind_invalid"),
        ({"approval_kind": None}, "governance_approval_kind_invalid"),
        ({"approval_kind": EdgeGateVerdict.PASS}, "governance_approval_kind_invalid"),
        ({"approved_envelope_id": ""}, "governance_approved_envelope_id_invalid"),
        ({"approved_envelope_version": None}, "governance_approved_envelope_version_invalid"),
        ({"approved_policy_digest": "g" * 64}, "governance_approved_policy_digest_invalid"),
        ({"approved_rule_set_digest": 7}, "governance_approved_rule_set_digest_invalid"),
    ],
)
def test_malformed_approval_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    with _raises(code):
        build(approval=approval_for(build(), **overrides))


@pytest.mark.parametrize("candidate", [{"approval_kind": "HUMAN_GOVERNANCE"}, "approved", 1, True, object()])
def test_approval_must_be_the_exact_record_type(candidate: object) -> None:
    with _raises("governance_approval_malformed"):
        build(approval=candidate)


def test_no_production_defaults_or_values_exist() -> None:
    signature = inspect.signature(build_paper_portfolio_risk_envelope)
    assert all(parameter.default is inspect.Parameter.empty for parameter in signature.parameters.values())
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    for record in (
        PaperPortfolioSleeveCap,
        PaperPortfolioMarketCap,
        PaperPortfolioCorrelationCap,
        PaperSleeveLadderBoundary,
        PaperPortfolioStopLevel,
        PaperPortfolioRiskEnvelopeApproval,
    ):
        assert all(item.default is dataclasses.MISSING for item in fields(record))
    governed_fields = {item.name for item in fields(PaperPortfolioRiskEnvelope)} - set(
        dict(PAPER_PORTFOLIO_RISK_ENVELOPE_NON_CLAIM_FLAGS)
    )
    assert all(
        item.default is dataclasses.MISSING
        for item in fields(PaperPortfolioRiskEnvelope)
        if item.name in governed_fields
    )
    tree = ast.parse(Path(envelope_module.__file__).read_text(encoding="utf-8"))
    constants = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)]
    # No decimal or multi-digit numeric text anywhere in the module: every governed number arrives from governance
    # input. Single digits are only the ASCII digit bounds of the decimal grammar.
    numeric_text = re.compile(r"-?(?:[0-9]+\.[0-9]+|[0-9]{2,})")
    assert not [value for value in constants if type(value) is str and numeric_text.fullmatch(value)]
    # The only integers are representation bounds, structural domain bounds and control-character limits.
    assert {value for value in constants if type(value) is int} <= {0, 1, 2, 18, 32, 60, 64, 127, 128, 256, INT64_MAX}


# --- B. budget and cap structure --------------------------------------------------------------------------------------

_SIXTY_CHARACTER_BUDGET = "9" * 41 + "." + "0" * 18


def test_canonical_total_budget_boundaries_are_accepted() -> None:
    assert len(_SIXTY_CHARACTER_BUDGET) == 60
    assert build(total_paper_risk_budget=_SIXTY_CHARACTER_BUDGET).total_paper_risk_budget == _SIXTY_CHARACTER_BUDGET
    smallest = "0." + "0" * 17 + "1"
    envelope = build(
        total_paper_risk_budget=smallest,
        sleeve_caps=[PaperPortfolioSleeveCap(sleeve_id="sleeve-alpha", max_paper_risk_budget=smallest)],
        market_caps=[PaperPortfolioMarketCap(market_symbol="BTC-PERPETUAL", max_paper_risk_budget=smallest)],
    )
    assert envelope.total_paper_risk_budget == smallest


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (d("0"), "total_paper_risk_budget_not_positive"),
        (d("-1"), "total_paper_risk_budget_not_positive"),
        ("1000", "total_paper_risk_budget_invalid"),
        ("1000.0", "total_paper_risk_budget_invalid"),
        ("1e3", "total_paper_risk_budget_invalid"),
        ("1.0e3", "total_paper_risk_budget_invalid"),
        (" " + d("1000"), "total_paper_risk_budget_invalid"),
        ("+" + d("1000"), "total_paper_risk_budget_invalid"),
        ("0" + d("1000"), "total_paper_risk_budget_invalid"),
        ("-" + d("0"), "total_paper_risk_budget_invalid"),
        ("1_000.000000000000000000", "total_paper_risk_budget_invalid"),
        ("NaN", "total_paper_risk_budget_invalid"),
        ("Infinity", "total_paper_risk_budget_invalid"),
        ("１000.000000000000000000", "total_paper_risk_budget_invalid"),
        ("9" * 42 + "." + "0" * 18, "total_paper_risk_budget_invalid"),
        (1000, "total_paper_risk_budget_invalid"),
        (1000.0, "total_paper_risk_budget_invalid"),
        (True, "total_paper_risk_budget_invalid"),
        (None, "total_paper_risk_budget_invalid"),
        (_Text(d("1000")), "total_paper_risk_budget_invalid"),
    ],
)
def test_total_budget_must_be_canonical_and_strictly_positive(value: object, code: str) -> None:
    with _raises(code):
        build(total_paper_risk_budget=value)


def test_multiple_caps_are_canonically_ordered_tuples() -> None:
    envelope = build(
        sleeve_caps=[sleeve("sleeve-gamma", "100"), sleeve("sleeve-alpha", "400"), sleeve("sleeve-beta", "250")],
        market_caps=[market("SOL-PERPETUAL", "100"), market("ETH-PERPETUAL", "500"), market("BTC-PERPETUAL", "600")],
    )
    assert [cap.sleeve_id for cap in envelope.sleeve_caps] == ["sleeve-alpha", "sleeve-beta", "sleeve-gamma"]
    assert [cap.market_symbol for cap in envelope.market_caps] == ["BTC-PERPETUAL", "ETH-PERPETUAL", "SOL-PERPETUAL"]
    assert type(envelope.sleeve_caps) is tuple
    assert type(envelope.market_caps) is tuple


def test_caps_equal_to_the_total_are_accepted() -> None:
    envelope = build(sleeve_caps=[sleeve("sleeve-alpha", "1000")], market_caps=[market("BTC-PERPETUAL", "1000")])
    assert envelope.sleeve_caps[0].max_paper_risk_budget == d("1000")
    assert envelope.market_caps[0].max_paper_risk_budget == d("1000")


def test_caps_need_not_sum_to_the_total() -> None:
    envelope = build(sleeve_caps=[sleeve("sleeve-alpha", "1000"), sleeve("sleeve-beta", "1000")])
    assert len(envelope.sleeve_caps) == 2


_ABOVE_TOTAL = "1000.000000000000000001"


@pytest.mark.parametrize(
    ("caps", "code"),
    [
        ([], "sleeve_caps_missing"),
        ((), "sleeve_caps_missing"),
        (None, "sleeve_caps_malformed"),
        ("sleeve-alpha", "sleeve_caps_malformed"),
        ({"sleeve-alpha": d("1")}, "sleeve_caps_malformed"),
        (frozenset({PaperPortfolioSleeveCap("sleeve-alpha", d("1"))}), "sleeve_caps_malformed"),
        (_List([PaperPortfolioSleeveCap("sleeve-alpha", d("1"))]), "sleeve_caps_malformed"),
        ([("sleeve-alpha", d("1"))], "sleeve_cap_malformed"),
        ([PaperPortfolioMarketCap("sleeve-alpha", d("1"))], "sleeve_cap_malformed"),
        ([_SleeveCapSubclass("sleeve-alpha", d("1"))], "sleeve_cap_malformed"),
        ([sleeve("sleeve-alpha", "400"), sleeve("sleeve-alpha", "300")], "sleeve_cap_duplicate"),
        ([sleeve("sleeve-alpha", "400"), sleeve("SLEEVE-ALPHA", "300")], "sleeve_cap_case_ambiguous"),
        ([PaperPortfolioSleeveCap("sleeve-alpha", _ABOVE_TOTAL)], "sleeve_cap_exceeds_total_paper_risk_budget"),
        ([sleeve("sleeve-alpha", "0")], "sleeve_cap_max_paper_risk_budget_not_positive"),
        ([sleeve("sleeve-alpha", "-5")], "sleeve_cap_max_paper_risk_budget_not_positive"),
        ([PaperPortfolioSleeveCap("sleeve-alpha", "400")], "sleeve_cap_max_paper_risk_budget_invalid"),
        ([PaperPortfolioSleeveCap("sleeve-alpha", 400.0)], "sleeve_cap_max_paper_risk_budget_invalid"),
        ([PaperPortfolioSleeveCap("sleeve-alpha", None)], "sleeve_cap_max_paper_risk_budget_invalid"),
    ],
)
def test_sleeve_caps_must_be_present_exact_unique_and_bounded(caps: object, code: str) -> None:
    with _raises(code):
        build(sleeve_caps=caps)


@pytest.mark.parametrize(
    ("caps", "code"),
    [
        ([], "market_caps_missing"),
        (None, "market_caps_malformed"),
        ([sleeve("BTC-PERPETUAL", "1")], "market_cap_malformed"),
        ([market("BTC-PERPETUAL", "600"), market("BTC-PERPETUAL", "500")], "market_cap_duplicate"),
        ([market("BTC-PERPETUAL", "600"), market("btc-perpetual", "500")], "market_cap_case_ambiguous"),
        ([PaperPortfolioMarketCap("BTC-PERPETUAL", _ABOVE_TOTAL)], "market_cap_exceeds_total_paper_risk_budget"),
        ([market("BTC-PERPETUAL", "0")], "market_cap_max_paper_risk_budget_not_positive"),
        ([PaperPortfolioMarketCap("BTC-PERPETUAL", "1e2")], "market_cap_max_paper_risk_budget_invalid"),
    ],
)
def test_market_caps_must_be_present_exact_unique_and_bounded(caps: object, code: str) -> None:
    with _raises(code):
        build(market_caps=caps)


@pytest.mark.parametrize(
    ("sleeve_id", "code"),
    [
        ("", "sleeve_id_invalid"),
        (" sleeve", "sleeve_id_invalid"),
        ("sleeve alpha", "sleeve_id_invalid"),
        ("sleeve#1", "sleeve_id_invalid"),
        ("-sleeve", "sleeve_id_invalid"),
        ("sléeve", "sleeve_id_invalid"),
        ("x" * 129, "sleeve_id_invalid"),
        (7, "sleeve_id_invalid"),
        (None, "sleeve_id_invalid"),
        (_Text("sleeve-alpha"), "sleeve_id_invalid"),
        ("live", "forbidden_scope_token:sleeve_id"),
        ("sleeve-scheduler", "forbidden_scope_token:sleeve_id"),
        ("bist-sleeve", "bist_scope_leakage:sleeve_id"),
    ],
)
def test_sleeve_ids_follow_the_identifier_grammar_and_scope_policy(sleeve_id: object, code: str) -> None:
    cap = PaperPortfolioSleeveCap(sleeve_id=sleeve_id, max_paper_risk_budget=d("1"))  # type: ignore[arg-type]
    with _raises(code):
        build(sleeve_caps=[cap])


@pytest.mark.parametrize("market_symbol", ["BTC PERPETUAL", "x" * 65, "", "BTC-PERPÉTUEL", ".BTC"])
def test_market_symbols_follow_the_identifier_grammar(market_symbol: str) -> None:
    with _raises("market_symbol_invalid"):
        build(market_caps=[PaperPortfolioMarketCap(market_symbol=market_symbol, max_paper_risk_budget=d("1"))])


def test_identifier_length_boundaries_are_accepted() -> None:
    envelope = build(sleeve_caps=[sleeve("s" * 128, "1")], market_caps=[market("M" * 64, "1")])
    assert envelope.sleeve_caps[0].sleeve_id == "s" * 128
    assert envelope.market_caps[0].market_symbol == "M" * 64


def test_max_sleeve_count_bounds_the_declared_sleeves() -> None:
    assert build(max_sleeve_count=2).max_sleeve_count == 2
    assert build(max_sleeve_count=INT64_MAX).max_sleeve_count == INT64_MAX
    with _raises("declared_sleeve_count_exceeds_max_sleeve_count"):
        build(max_sleeve_count=1)


@pytest.mark.parametrize("value", [0, -1, True, False, "3", 3.0, None, INT64_MAX + 1, _Int(3)])
def test_invalid_max_sleeve_count_is_refused(value: object) -> None:
    with _raises("max_sleeve_count_invalid"):
        build(max_sleeve_count=value)


# --- C. correlation structure -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("cap", ["-1", "-0.999999999999999999", "0", "0.6", "0.999999999999999999"])
def test_correlation_cap_domain_is_minus_one_inclusive_to_one_exclusive(cap: str) -> None:
    assert build(correlation_cap=correlation(cap=cap)).correlation_cap.max_pairwise_correlation == d(cap)


@pytest.mark.parametrize("cap", ["1", "1.000000000000000001", "2", "-1.000000000000000001", "-2"])
def test_correlation_cap_outside_the_domain_is_refused(cap: str) -> None:
    with _raises("max_pairwise_correlation_out_of_domain"):
        build(correlation_cap=correlation(cap=cap))


def test_worst_case_unknown_correlation_breaches_every_legal_cap() -> None:
    rule_set = paper_portfolio_risk_envelope_rule_set()
    worst_case = Fraction(1)
    assert "worst_case_one" in str(rule_set["unknown_correlation_rule_id"])
    assert "breach_iff_strictly_beyond" in str(rule_set["limit_rule_id"])
    assert Fraction(rule_set["correlation_cap_upper_bound_exclusive"]) == worst_case  # type: ignore[arg-type]
    for cap in ("-1", "0", "0.6", "0.999999999999999999"):
        legal = build(correlation_cap=correlation(cap=cap)).correlation_cap.max_pairwise_correlation
        # Under inclusive limits a value is within the cap iff it is at most the cap; the worst case never is.
        assert worst_case > Fraction(legal)


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (None, "correlation_cap_missing"),
        ({"max_pairwise_correlation": d("0.6")}, "correlation_cap_malformed"),
        (0.6, "correlation_cap_malformed"),
        (PaperPortfolioCorrelationCap(0.6, 60, 30), "max_pairwise_correlation_invalid"),  # type: ignore[arg-type]
        (PaperPortfolioCorrelationCap("0.6", 60, 30), "max_pairwise_correlation_invalid"),
        (PaperPortfolioCorrelationCap(None, 60, 30), "max_pairwise_correlation_invalid"),  # type: ignore[arg-type]
        (correlation(overlap=1), "min_overlap_days_invalid"),
        (correlation(overlap=0), "min_overlap_days_invalid"),
        (correlation(overlap=30.0), "min_overlap_days_invalid"),
        (correlation(overlap=_Int(30)), "min_overlap_days_invalid"),
        (correlation(lookback=0), "lookback_window_days_invalid"),
        (correlation(lookback=True), "lookback_window_days_invalid"),
        (correlation(lookback=INT64_MAX + 1), "lookback_window_days_invalid"),
        (correlation(lookback=29, overlap=30), "min_overlap_days_exceeds_lookback_window_days"),
    ],
)
def test_missing_or_malformed_correlation_structure_is_refused(value: object, code: str) -> None:
    with _raises(code):
        build(correlation_cap=value)


def test_correlation_window_boundaries_are_accepted() -> None:
    assert build(correlation_cap=correlation(lookback=2, overlap=2)).correlation_cap.min_overlap_days == 2
    assert build(correlation_cap=correlation(lookback=60, overlap=60)).correlation_cap.lookback_window_days == 60
    assert build(correlation_cap=correlation(lookback=INT64_MAX, overlap=2)).correlation_cap.lookback_window_days == (
        INT64_MAX
    )


# --- D. drawdown and portfolio-stop structure -------------------------------------------------------------------------


def test_stop_levels_are_canonically_ordered_by_level() -> None:
    envelope = build(portfolio_stop_levels=[stop(3, "0.15"), stop(1, "0.05"), stop(2, "0.1")])
    assert [level.stop_level for level in envelope.portfolio_stop_levels] == [1, 2, 3]
    assert envelope.portfolio_stop_levels == build().portfolio_stop_levels
    assert type(envelope.portfolio_stop_levels) is tuple


@pytest.mark.parametrize(
    ("levels", "code"),
    [
        ([], "portfolio_stop_levels_missing"),
        (None, "portfolio_stop_levels_malformed"),
        ({1: d("0.05")}, "portfolio_stop_levels_malformed"),
        ([(1, d("0.05"))], "portfolio_stop_level_malformed"),
        ([stop(1, "0.05"), stop(1, "0.1")], "portfolio_stop_level_duplicate"),
        ([stop(1, "0.1"), stop(2, "0.1")], "portfolio_stop_level_threshold_ambiguous"),
        ([stop(1, "0.1"), stop(2, "0.05")], "portfolio_stop_level_thresholds_not_increasing"),
        ([stop(1, "0.05"), stop(2, "0.1"), stop(3, "0.07")], "portfolio_stop_level_thresholds_not_increasing"),
        ([stop(1, "0.05"), stop(3, "0.15")], "portfolio_stop_levels_not_contiguous_from_one"),
        ([stop(2, "0.05")], "portfolio_stop_levels_not_contiguous_from_one"),
        ([stop(0, "0.05")], "stop_level_invalid"),
        ([stop(True, "0.05")], "stop_level_invalid"),
        ([stop("1", "0.05")], "stop_level_invalid"),
        ([PaperPortfolioStopLevel(1, "0.05")], "max_portfolio_drawdown_fraction_invalid"),
        ([PaperPortfolioStopLevel(1, 0.05)], "max_portfolio_drawdown_fraction_invalid"),  # type: ignore[arg-type]
        ([stop(1, "1")], "max_portfolio_drawdown_fraction_out_of_domain"),
        ([stop(1, "1.5")], "max_portfolio_drawdown_fraction_out_of_domain"),
        ([stop(1, "-0.05")], "max_portfolio_drawdown_fraction_out_of_domain"),
    ],
)
def test_portfolio_stop_ladder_must_be_present_contiguous_and_strictly_increasing(levels: object, code: str) -> None:
    with _raises(code):
        build(portfolio_stop_levels=levels)


@pytest.mark.parametrize("threshold", ["0", "0.000000000000000001", "0.999999999999999999"])
def test_drawdown_domain_is_zero_inclusive_to_one_exclusive(threshold: str) -> None:
    envelope = build(portfolio_stop_levels=[stop(1, threshold)])
    assert envelope.portfolio_stop_levels[0].max_portfolio_drawdown_fraction == d(threshold)


def test_declared_limit_semantics_are_inclusive_and_committed() -> None:
    rule_set = paper_portfolio_risk_envelope_rule_set()
    assert rule_set["limit_rule_id"] == (
        "inclusive_limits_within_iff_at_most_ceiling_or_at_least_floor_breach_iff_strictly_beyond.v1"
    )
    assert rule_set["drawdown_lower_bound_inclusive"] == 0
    assert rule_set["drawdown_upper_bound_exclusive"] == 1
    assert "strictly_increasing" in str(rule_set["portfolio_stop_rule_id"])


# --- E. promotion and demotion ladder ---------------------------------------------------------------------------------


def test_ladder_is_canonically_ordered_lowest_boundary_first() -> None:
    envelope = build(ladder_boundaries=[upper_boundary(), lower_boundary()])
    assert [(item.lower_tier, item.upper_tier) for item in envelope.ladder_boundaries] == [
        (PROBATION, STANDARD),
        (STANDARD, EXPANDED),
    ]
    assert envelope.ladder_boundaries == build().ladder_boundaries


def test_ladder_tier_text_is_canonicalized_to_the_exact_member() -> None:
    envelope = build(ladder_boundaries=[boundary("PROBATION", "STANDARD"), upper_boundary()])
    assert type(envelope.ladder_boundaries[0].lower_tier) is PaperSleeveLadderTier
    assert envelope.ladder_boundaries[0].lower_tier is PROBATION


@pytest.mark.parametrize(
    ("boundaries", "code"),
    [
        ([], "ladder_boundaries_missing"),
        (None, "ladder_boundaries_malformed"),
        ({"PROBATION": "STANDARD"}, "ladder_boundaries_malformed"),
        ([lower_boundary()], "ladder_boundaries_incomplete"),
        ([upper_boundary()], "ladder_boundaries_incomplete"),
        ([lower_boundary(), lower_boundary(), upper_boundary()], "ladder_boundary_duplicate"),
        ([lower_boundary(), upper_boundary(), boundary(PROBATION, EXPANDED)], "ladder_boundary_not_adjacent_ascending"),
        ([boundary(STANDARD, PROBATION), upper_boundary()], "ladder_boundary_not_adjacent_ascending"),
        ([boundary(STANDARD, STANDARD), upper_boundary()], "ladder_boundary_not_adjacent_ascending"),
        ([boundary("PROBATIONARY", STANDARD), upper_boundary()], "ladder_lower_tier_invalid"),
        ([boundary(PROBATION, None), upper_boundary()], "ladder_upper_tier_invalid"),
        ([boundary(PROBATION, _Text("STANDARD")), upper_boundary()], "ladder_upper_tier_invalid"),
        ([{"lower_tier": "PROBATION"}, upper_boundary()], "ladder_boundary_malformed"),
    ],
)
def test_ladder_boundaries_must_be_exactly_the_adjacent_ascending_pairs(boundaries: object, code: str) -> None:
    with _raises(code):
        build(ladder_boundaries=boundaries)


@pytest.mark.parametrize(
    ("lower", "upper", "code"),
    [
        ({"promotion_sharpe": "-0.1"}, {}, "ladder_promotion_sharpe_floor_below_demotion_sharpe_floor"),
        ({"demotion_sharpe": "1.6"}, {}, "ladder_promotion_sharpe_floor_below_demotion_sharpe_floor"),
        ({}, {"promotion_sharpe": "0.4"}, "ladder_promotion_sharpe_floor_below_demotion_sharpe_floor"),
        ({"promotion_drawdown": "0.21"}, {}, "ladder_promotion_drawdown_ceiling_above_demotion_drawdown_ceiling"),
        ({}, {"demotion_drawdown": "0.07"}, "ladder_promotion_drawdown_ceiling_above_demotion_drawdown_ceiling"),
        (
            {"demotion_sharpe": "0.9"},
            {"promotion_sharpe": "0.8", "demotion_sharpe": "0.5"},
            "ladder_middle_tier_promotion_sharpe_floor_below_demotion_sharpe_floor",
        ),
        (
            {"promotion_drawdown": "0.1", "demotion_drawdown": "0.12"},
            {"promotion_drawdown": "0.13", "demotion_drawdown": "0.15"},
            "ladder_middle_tier_promotion_drawdown_ceiling_above_demotion_drawdown_ceiling",
        ),
    ],
)
def test_reversed_or_contradictory_ladder_levels_are_refused(
    lower: dict[str, object], upper: dict[str, object], code: str
) -> None:
    with _raises(code):
        build(ladder_boundaries=[lower_boundary(**lower), upper_boundary(**upper)])


def test_ladder_level_equalities_are_consistent_and_accepted() -> None:
    flat = {
        "promotion_sharpe": "0.5",
        "demotion_sharpe": "0.5",
        "promotion_drawdown": "0.1",
        "demotion_drawdown": "0.1",
    }
    envelope = build(ladder_boundaries=[lower_boundary(**flat), upper_boundary(**flat)])
    assert {item.promotion_min_paper_sharpe for item in envelope.ladder_boundaries} == {d("0.5")}


def test_paper_sharpe_levels_are_signed_governed_values() -> None:
    envelope = build(
        ladder_boundaries=[
            lower_boundary(promotion_sharpe="-0.5", demotion_sharpe="-1"),
            upper_boundary(promotion_sharpe="-0.25", demotion_sharpe="-0.5"),
        ]
    )
    assert envelope.ladder_boundaries[0].demotion_min_paper_sharpe == d("-1")


def _promotion_eligible(item: PaperSleeveLadderBoundary, sharpe: Fraction, drawdown: Fraction) -> bool:
    if sharpe < Fraction(item.promotion_min_paper_sharpe):
        return False
    return drawdown <= Fraction(item.promotion_max_drawdown_fraction)


def _demotion_eligible(item: PaperSleeveLadderBoundary, sharpe: Fraction, drawdown: Fraction) -> bool:
    if sharpe < Fraction(item.demotion_min_paper_sharpe):
        return True
    return drawdown > Fraction(item.demotion_max_drawdown_fraction)


def _probe_points(levels: set[Fraction], *, low: Fraction, high: Fraction) -> list[Fraction]:
    ordered = sorted(levels | {low, high})
    midpoints = [(left + right) / 2 for left, right in zip(ordered, ordered[1:])]
    return sorted(set(ordered) | set(midpoints))


@pytest.mark.parametrize(
    "ladder",
    [
        [lower_boundary(), upper_boundary()],
        [
            lower_boundary(
                promotion_sharpe="0.5", demotion_sharpe="0.5", promotion_drawdown="0.1", demotion_drawdown="0.1"
            ),
            upper_boundary(
                promotion_sharpe="0.5", demotion_sharpe="0.5", promotion_drawdown="0.1", demotion_drawdown="0.1"
            ),
        ],
    ],
    ids=["banded", "zero_width"],
)
def test_accepted_ladder_never_makes_one_snapshot_both_promotion_and_demotion_eligible(
    ladder: list[PaperSleeveLadderBoundary],
) -> None:
    lower, upper = build(ladder_boundaries=ladder).ladder_boundaries
    sharpe_levels = {
        Fraction(text)
        for item in (lower, upper)
        for text in (item.promotion_min_paper_sharpe, item.demotion_min_paper_sharpe)
    }
    drawdown_levels = {
        Fraction(text)
        for item in (lower, upper)
        for text in (item.promotion_max_drawdown_fraction, item.demotion_max_drawdown_fraction)
    }
    sharpes = _probe_points(sharpe_levels, low=Fraction(-10), high=Fraction(10))
    drawdowns = _probe_points(drawdown_levels, low=Fraction(0), high=Fraction(999, 1000))
    for sharpe in sharpes:
        for drawdown in drawdowns:
            # A sleeve promoted into a boundary's upper tier is never demotion-eligible from it on the same snapshot.
            for item in (lower, upper):
                if _promotion_eligible(item, sharpe, drawdown):
                    assert not _demotion_eligible(item, sharpe, drawdown)
            # The middle tier is never both promotion-eligible upward and demotion-eligible downward.
            if _promotion_eligible(upper, sharpe, drawdown):
                assert not _demotion_eligible(lower, sharpe, drawdown)


@pytest.mark.parametrize("value", [0, -1, True, "30", 30.0, None, INT64_MAX + 1, _Int(30)])
def test_invalid_probation_window_is_refused(value: object) -> None:
    with _raises("min_probation_days_invalid"):
        build(ladder_boundaries=[lower_boundary(probation=value), upper_boundary()])


def test_probation_window_boundaries_are_accepted() -> None:
    envelope = build(ladder_boundaries=[lower_boundary(probation=1), upper_boundary(probation=INT64_MAX)])
    assert [item.min_probation_days for item in envelope.ladder_boundaries] == [1, INT64_MAX]


@pytest.mark.parametrize(
    ("field_name", "value", "code"),
    [
        ("promotion_min_paper_sharpe", "1", "promotion_min_paper_sharpe_invalid"),
        ("promotion_min_paper_sharpe", 1.0, "promotion_min_paper_sharpe_invalid"),
        ("demotion_min_paper_sharpe", None, "demotion_min_paper_sharpe_invalid"),
        ("promotion_max_drawdown_fraction", d("1"), "promotion_max_drawdown_fraction_out_of_domain"),
        ("promotion_max_drawdown_fraction", d("-0.1"), "promotion_max_drawdown_fraction_out_of_domain"),
        ("demotion_max_drawdown_fraction", "0.2", "demotion_max_drawdown_fraction_invalid"),
        ("demotion_max_drawdown_fraction", d("1.2"), "demotion_max_drawdown_fraction_out_of_domain"),
    ],
)
def test_malformed_ladder_levels_are_refused(field_name: str, value: object, code: str) -> None:
    with _raises(code):
        build(ladder_boundaries=[replace(lower_boundary(), **{field_name: value}), upper_boundary()])


def test_envelope_stores_the_constitution_and_decides_nothing() -> None:
    envelope = governed()
    assert envelope.promotion_demotion_decided is False
    assert envelope.portfolio_stop_evaluated is False
    assert envelope.portfolio_allocation_approved is False
    assert envelope.performance_data_consumed is False
    decision_words = ("decide", "evaluate", "allocate", "promote", "demote", "apply")
    assert not [name for name in envelope_module.__all__ if any(word in name.lower() for word in decision_words)]


# --- F. digest and serialization --------------------------------------------------------------------------------------


def test_serialization_is_deterministic_across_insertion_orders_and_sequence_types() -> None:
    first = governed()
    args = envelope_args()
    permuted = build(
        approval=first.approval,
        sleeve_caps=tuple(reversed(args["sleeve_caps"])),  # type: ignore[arg-type]
        market_caps=tuple(reversed(args["market_caps"])),  # type: ignore[arg-type]
        ladder_boundaries=tuple(reversed(args["ladder_boundaries"])),  # type: ignore[arg-type]
        portfolio_stop_levels=tuple(reversed(args["portfolio_stop_levels"])),  # type: ignore[arg-type]
    )
    assert permuted == first
    assert edge_canonical_json(to_dict(permuted)) == edge_canonical_json(to_dict(first))
    assert permuted.envelope_digest == first.envelope_digest
    assert build() == build()


def test_digests_recompute_and_the_payload_round_trips() -> None:
    for envelope in (build(), governed(), build(approval=approval_for(build(), kind=SYNTHETIC))):
        payload = to_dict(envelope)
        assert paper_portfolio_risk_envelope_digest(envelope) == envelope.envelope_digest
        assert payload["envelope_digest"] == envelope.envelope_digest
        assert _policy_digest_of(payload) == envelope.policy_digest
        wire = json.loads(json.dumps(payload))
        assert paper_portfolio_risk_envelope_payload_is_well_formed(wire) is True
        assert paper_portfolio_risk_envelope_from_payload(wire) == envelope
        _assert_intact(envelope)


def test_policy_digest_excludes_only_the_approval_verdict_and_digests() -> None:
    unapproved = build()
    for envelope in (governed(), build(approval=approval_for(build(), kind=SYNTHETIC))):
        assert envelope.policy_digest == unapproved.policy_digest
    payload = to_dict(unapproved)
    assert set(payload) - _NON_POLICY_FIELDS >= {
        "schema_version",
        "envelope_id",
        "envelope_version",
        "rule_set_id",
        "rule_set_digest",
        "total_paper_risk_budget",
        "sleeve_caps",
        "market_caps",
        "max_sleeve_count",
        "correlation_cap",
        "ladder_boundaries",
        "portfolio_stop_levels",
        "regime_stratified_correlation_status",
        "regime_concentration_demotion_status",
        "paper_only",
        "execution_authorized",
    }


def test_rule_set_digest_commits_the_rule_set_the_module_reads() -> None:
    rule_set = paper_portfolio_risk_envelope_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST
    envelope = build()
    assert envelope.rule_set_digest == PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST
    assert envelope.rule_set_id == rule_set["rule_set_id"]
    assert rule_set["ladder_tiers"] == tuple(tier.value for tier in PaperSleeveLadderTier)
    assert rule_set["decimal_scale"] == 18
    assert rule_set["decimal_max_text_length"] == 60
    assert rule_set["max_wire_integer"] == INT64_MAX
    assert rule_set["correlation_min_overlap_floor_days"] == 2
    assert rule_set["performance_measure_id"] == "paper-sharpe-evidence.v1:paper_sharpe_annualized"
    rule_set["decimal_scale"] = 2
    assert paper_portfolio_risk_envelope_rule_set()["decimal_scale"] == 18


def test_stale_self_digest_is_rejected() -> None:
    verification = verify(replace(governed(), envelope_digest="0" * 64))
    assert verification.intact is False
    assert _code("self_digest_mismatch") in verification.reason_codes


@pytest.mark.parametrize(
    "changes",
    [
        {"total_paper_risk_budget": d("5000")},
        {"sleeve_caps": (sleeve("sleeve-alpha", "999"), sleeve("sleeve-beta", "250"))},
        {"market_caps": (market("BTC-PERPETUAL", "999"), market("ETH-PERPETUAL", "500"))},
        {"max_sleeve_count": 9},
        {"correlation_cap": correlation(cap="0.9")},
        {"ladder_boundaries": (lower_boundary(probation=1), upper_boundary())},
        {"portfolio_stop_levels": (stop(1, "0.5"),)},
    ],
    ids=lambda change: next(iter(change)),
)
def test_resealed_semantic_mutation_is_rejected(changes: dict[str, object]) -> None:
    verification = verify(_reseal(governed(), **changes))
    assert verification.intact is False
    assert _code("field_mismatch:policy_digest") in verification.reason_codes
    # The approval binds the old policy, so the reassembled verdict no longer passes.
    assert _code("field_mismatch:gate_verdict") in verification.reason_codes
    assert _code("field_mismatch:advances") in verification.reason_codes


def test_resealed_mutation_with_a_recomputed_policy_digest_cannot_keep_pass() -> None:
    mutated = replace(governed(), total_paper_risk_budget=d("5000"))
    mutated = replace(mutated, policy_digest=_policy_digest_of(to_dict(mutated)))
    forged = replace(mutated, envelope_digest=paper_portfolio_risk_envelope_digest(mutated))
    verification = verify(forged)
    assert verification.intact is False
    assert _code("field_mismatch:policy_digest") not in verification.reason_codes
    assert {
        _code("field_mismatch:gate_verdict"),
        _code("field_mismatch:advances"),
        _code("field_mismatch:verdict_reason_codes"),
    } <= set(verification.reason_codes)


def test_resealed_invalid_constitution_is_rejected() -> None:
    verification = verify(_reseal(governed(), max_sleeve_count=1))
    assert verification.intact is False
    assert verification.reason_codes == (_code("evidence_reassembly_failed"),)


@pytest.mark.parametrize(
    "artifact",
    [
        pytest.param(None, id="none"),
        pytest.param(1, id="int"),
        pytest.param("envelope", id="str"),
        pytest.param(b"envelope", id="bytes"),
        pytest.param({}, id="dict"),
        pytest.param(object(), id="object"),
        pytest.param(object.__new__(PaperPortfolioRiskEnvelope), id="uninitialized"),
        pytest.param(_corrupted(sleeve_caps=None), id="sleeve_caps_none"),
        pytest.param(_corrupted(sleeve_caps=[sleeve("sleeve-alpha", "400"), sleeve("sleeve-beta", "250")]), id="list"),
        pytest.param(_corrupted(sleeve_caps=({"sleeve_id": "sleeve-alpha"},)), id="sleeve_cap_dict"),
        pytest.param(_corrupted(market_caps=()), id="market_caps_empty"),
        pytest.param(_corrupted(correlation_cap="0.6"), id="correlation_text"),
        pytest.param(_corrupted(ladder_boundaries=(lower_boundary(),)), id="ladder_incomplete"),
        pytest.param(_corrupted(portfolio_stop_levels=(stop(2, "0.1"),)), id="stop_gap"),
        pytest.param(_corrupted(max_sleeve_count=10**5000), id="huge_int"),
        pytest.param(_corrupted(max_sleeve_count=True), id="bool_int"),
        pytest.param(_corrupted(total_paper_risk_budget=1000.0), id="float_budget"),
        pytest.param(_corrupted(gate_verdict="PASS"), id="verdict_alias"),
        pytest.param(_corrupted(approval={"approval_kind": "HUMAN_GOVERNANCE"}), id="approval_dict"),
        pytest.param(_corrupted(approval=None), id="approval_removed"),
        pytest.param(_corrupted(advances=False), id="advances_flipped"),
        pytest.param(_corrupted(synthetic_test_approval_used=True), id="synthetic_flag"),
        pytest.param(_corrupted(regime_stratified_correlation_status="AVAILABLE"), id="regime_status"),
        pytest.param(_corrupted(rule_set_digest="0" * 64), id="rule_set_digest"),
        pytest.param(_corrupted(policy_digest="0" * 64), id="policy_digest"),
        pytest.param(_corrupted(live_ready=True), id="live_ready"),
        pytest.param(_corrupted(execution_authorized=1), id="execution_authorized_int"),
        pytest.param(_corrupted(envelope_id=_Text("rg2-synthetic-envelope")), id="text_subclass"),
        pytest.param(_corrupted(verdict_reason_codes=["x"]), id="reason_list"),
    ],
)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify(artifact)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


def test_str_enum_aliases_inside_the_artifact_fail_verification() -> None:
    envelope = governed()
    approval = replace(envelope.approval)  # type: ignore[arg-type]
    object.__setattr__(approval, "approval_kind", "HUMAN_GOVERNANCE")
    aliased_approval = replace(envelope)
    object.__setattr__(aliased_approval, "approval", approval)
    tier = replace(envelope.ladder_boundaries[0])
    object.__setattr__(tier, "lower_tier", "PROBATION")
    aliased_tier = replace(envelope)
    object.__setattr__(aliased_tier, "ladder_boundaries", (tier, envelope.ladder_boundaries[1]))
    for candidate in (aliased_approval, aliased_tier):
        verification = verify(candidate)
        assert verification.intact is False
        assert verification.reason_codes == (_code("evidence_serialization_failed"),)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("max_sleeve_count",), INT64_MAX + 1),
        (("max_sleeve_count",), -1),
        (("max_sleeve_count",), True),
        (("total_paper_risk_budget",), 1000),
        (("total_paper_risk_budget",), "1000"),
        (("total_paper_risk_budget",), "9" * 42 + "." + "0" * 18),
        (("sleeve_caps",), {}),
        (("sleeve_caps", 0, "max_paper_risk_budget"), "400"),
        (("sleeve_caps", 0, "sleeve_id"), 7),
        (("sleeve_caps", 0, "unexpected"), "x"),
        (("correlation_cap",), None),
        (("correlation_cap", "min_overlap_days"), "30"),
        (("ladder_boundaries", 0, "lower_tier"), "PROBATIONARY"),
        (("ladder_boundaries", 0, "min_probation_days"), 1.5),
        (("portfolio_stop_levels", 0, "stop_level"), False),
        (("approval",), {"approval_kind": "HUMAN_GOVERNANCE"}),
        (("approval", "approval_kind"), "ROBOT"),
        (("gate_verdict",), "ACCEPTED"),
        (("advances",), "true"),
        (("verdict_reason_codes",), "none"),
        (("live_ready",), None),
        (("synthetic_test_approval_used",), 0),
    ],
    ids=lambda value: str(value)[:30],
)
def test_parser_refuses_states_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    payload = json.loads(json.dumps(to_dict(governed())))
    target: object = payload
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    assert paper_portfolio_risk_envelope_payload_is_well_formed(payload) is False


def test_parser_refuses_a_missing_field() -> None:
    payload = json.loads(json.dumps(to_dict(governed())))
    del payload["policy_digest"]
    assert paper_portfolio_risk_envelope_payload_is_well_formed(payload) is False


def test_caller_containers_are_read_once_and_never_alias_the_artifact() -> None:
    sleeves = [sleeve("sleeve-alpha", "400"), sleeve("sleeve-beta", "250")]
    markets = [market("BTC-PERPETUAL", "600"), market("ETH-PERPETUAL", "500")]
    ladder = [lower_boundary(), upper_boundary()]
    stops = [stop(1, "0.05"), stop(2, "0.1"), stop(3, "0.15")]
    originals = (list(sleeves), list(markets), list(ladder), list(stops))
    envelope = build(sleeve_caps=sleeves, market_caps=markets, ladder_boundaries=ladder, portfolio_stop_levels=stops)
    assert (sleeves, markets, ladder, stops) == originals
    before = to_dict(envelope)
    sleeves.append(sleeve("sleeve-gamma", "999"))
    markets.clear()
    ladder.reverse()
    stops.pop()
    assert to_dict(envelope) == before
    _assert_intact(envelope)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"envelope_id": ""}, "envelope_id_invalid"),
        ({"envelope_id": " rg2"}, "envelope_id_invalid"),
        ({"envelope_id": "rg2\tenvelope"}, "envelope_id_invalid"),
        ({"envelope_id": "x" * 257}, "envelope_id_invalid"),
        ({"envelope_id": None}, "envelope_id_invalid"),
        ({"envelope_id": _Text("rg2-synthetic-envelope")}, "envelope_id_invalid"),
        ({"envelope_version": "live-v1"}, "forbidden_scope_token:envelope_version"),
        ({"envelope_id": "borsa-envelope"}, "bist_scope_leakage:envelope_id"),
        ({"max_sleeve_count": _Int(3)}, "max_sleeve_count_invalid"),
        ({"sleeve_caps": [PaperPortfolioSleeveCap(_Text("sleeve-alpha"), d("400"))]}, "sleeve_id_invalid"),
        (
            {"sleeve_caps": [PaperPortfolioSleeveCap("sleeve-alpha", _Text(d("400")))]},
            "sleeve_cap_max_paper_risk_budget_invalid",
        ),
        ({"correlation_cap": correlation(lookback=_Int(60))}, "lookback_window_days_invalid"),
    ],
)
def test_exact_types_and_identity_text_are_required(overrides: dict[str, object], code: str) -> None:
    with _raises(code):
        build(**overrides)


def test_artifacts_are_frozen_and_hold_tuples() -> None:
    envelope = governed()
    with pytest.raises(FrozenInstanceError):
        envelope.advances = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        envelope.sleeve_caps[0].max_paper_risk_budget = d("1")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        envelope.approval.approved_policy_digest = "0" * 64  # type: ignore[misc,union-attr]
    for name in ("sleeve_caps", "market_caps", "ladder_boundaries", "portfolio_stop_levels", "verdict_reason_codes"):
        assert type(getattr(envelope, name)) is tuple


# --- G. safety and non-overclaim --------------------------------------------------------------------------------------


def test_paper_only_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flags = dict(PAPER_PORTFOLIO_RISK_ENVELOPE_NON_CLAIM_FLAGS)
    assert set(dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)) <= set(flags)
    assert {
        "execution_authorized",
        "portfolio_allocation_approved",
        "capital_allocated",
        "prdv4_stage4_complete",
        "live_ready",
        "shadow_ready",
        "operational_readiness",
        "edge_proven",
        "profitability_proven",
        "real_orders_enabled",
        "real_money_enabled",
        "real_capital_reserved",
        "current_lifecycle_head_proven",
    } <= set(flags)
    assert flags["paper_only"] is True
    assert {value for name, value in flags.items() if name != "paper_only"} == {False}
    defaults = {item.name: item.default for item in fields(PaperPortfolioRiskEnvelope) if item.name in flags}
    assert defaults == flags
    assert not set(flags) & set(inspect.signature(build_paper_portfolio_risk_envelope).parameters)
    for envelope in (build(), governed()):
        for name, value in PAPER_PORTFOLIO_RISK_ENVELOPE_NON_CLAIM_FLAGS:
            assert getattr(envelope, name) is value


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("execution_authorized", True),
        ("portfolio_allocation_approved", True),
        ("capital_allocated", True),
        ("live_ready", True),
        ("shadow_ready", True),
        ("operational_readiness", True),
        ("edge_proven", True),
        ("profitability_proven", True),
        ("real_money_enabled", True),
        ("real_orders_enabled", True),
        ("prdv4_stage4_complete", True),
        ("current_lifecycle_head_proven", True),
        ("paper_only", False),
    ],
)
def test_forged_non_claim_flags_fail_verification(flag: str, value: bool) -> None:
    verification = verify(_reseal(governed(), **{flag: value}))
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


def test_regime_dependent_structure_stays_pending_and_digest_bound() -> None:
    envelope = governed()
    assert envelope.regime_stratified_correlation_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert envelope.regime_concentration_demotion_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert envelope.regime_evidence_available is False
    parameters = set(inspect.signature(build_paper_portfolio_risk_envelope).parameters)
    for name in ("regime_stratified_correlation_status", "regime_concentration_demotion_status"):
        assert name not in parameters
        verification = verify(_reseal(envelope, **{name: "AVAILABLE"}))
        assert verification.intact is False
        assert _code(f"field_mismatch:{name}") in verification.reason_codes


def test_module_is_pure_and_consumes_only_the_edge_kernel() -> None:
    pit.assert_module_is_pure(envelope_module, {"crypto_core.validation.edge_artifact_core"})


def test_module_imports_only_the_standard_pure_surface_and_the_kernel() -> None:
    tree = ast.parse(Path(envelope_module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    assert imported == {
        "__future__",
        "collections.abc",
        "dataclasses",
        "enum",
        "fractions",
        "itertools",
        "crypto_core.validation.edge_artifact_core",
    }


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    pit.assert_single_assembly_path(
        envelope_module,
        "PaperPortfolioRiskEnvelope",
        "_assemble_envelope",
        "build_paper_portfolio_risk_envelope",
        "_reassemble_envelope",
    )


def test_public_api_is_exact() -> None:
    assert set(envelope_module.__all__) == {
        "PAPER_PORTFOLIO_RISK_ENVELOPE_NON_CLAIM_FLAGS",
        "PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST",
        "PaperPortfolioCorrelationCap",
        "PaperPortfolioMarketCap",
        "PaperPortfolioRiskEnvelope",
        "PaperPortfolioRiskEnvelopeApproval",
        "PaperPortfolioRiskEnvelopeApprovalKind",
        "PaperPortfolioRiskEnvelopeError",
        "PaperPortfolioSleeveCap",
        "PaperPortfolioStopLevel",
        "PaperSleeveLadderBoundary",
        "PaperSleeveLadderTier",
        "build_paper_portfolio_risk_envelope",
        "paper_portfolio_risk_envelope_digest",
        "paper_portfolio_risk_envelope_from_payload",
        "paper_portfolio_risk_envelope_payload_is_well_formed",
        "paper_portfolio_risk_envelope_rule_set",
        "paper_portfolio_risk_envelope_to_dict",
        "verify_paper_portfolio_risk_envelope",
    }
    assert all(hasattr(envelope_module, name) for name in envelope_module.__all__)
