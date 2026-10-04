"""Paper sleeve funding evidence contract tests (PAPER_SLEEVE_FUNDING_EVIDENCE_V1).

SYNTHETIC TEST VALUES ONLY. Every funding amount, instant and digest below is a synthetic test value that exercises the
contract. None is a venue funding rate, a production funding amount or venue truth.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.paper_sleeve_funding_evidence as funding_module
from crypto_core.validation.edge_artifact_core import EdgeEvidenceVerification, edge_canonical_json, edge_sha256_text
from crypto_core.validation.paper_sleeve_funding_evidence import (
    PAPER_SLEEVE_FUNDING_EVIDENCE_NON_CLAIM_FLAGS,
    PAPER_SLEEVE_FUNDING_EVIDENCE_RULE_SET_DIGEST,
    PaperSleeveFundingEvent,
    PaperSleeveFundingEvidence,
    PaperSleeveFundingEvidenceError,
    build_paper_sleeve_funding_evidence,
    paper_sleeve_funding_evidence_digest,
    paper_sleeve_funding_evidence_from_payload,
    paper_sleeve_funding_evidence_payload_is_well_formed,
    paper_sleeve_funding_evidence_rule_set,
    paper_sleeve_funding_evidence_to_dict,
    verify_paper_sleeve_funding_evidence,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

_PREFIX = "paper_sleeve_funding_evidence"
DAY_NS = 86_400_000_000_000
HOUR_NS = 3_600_000_000_000
START = 20_454 * DAY_NS
END = START + 3 * DAY_NS
INT64_MAX = 9223372036854775807


class _Text(str):
    """A ``str`` subclass, refused wherever exact text is required."""


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _raises(code: str):
    """``pytest.raises`` for one exact prefixed construction-error code."""

    return pytest.raises(PaperSleeveFundingEvidenceError, match=re.escape(_code(code)))


def d(text: str) -> str:
    """A SYNTHETIC TEST VALUE rendered as canonical scale-18 decimal text."""

    negative = text.startswith("-")
    integer, _, fraction = text.lstrip("-").partition(".")
    rendered = f"{integer}.{fraction.ljust(18, '0')}"
    return f"-{rendered}" if negative else rendered


def event(index: int, amount: str = "-0.01", **overrides: object) -> PaperSleeveFundingEvent:
    values: dict[str, object] = {
        "event_id": f"funding-{index}",
        "settlement_at_ns": START + index * DAY_NS + 8 * HOUR_NS,
        "position_state_digest": f"{index:x}" * 64 if index < 16 else "e" * 64,
        "funding_amount": d(amount),
    }
    values.update(overrides)
    return PaperSleeveFundingEvent(**values)  # type: ignore[arg-type]


def build(**overrides: object) -> PaperSleeveFundingEvidence:
    values: dict[str, object] = {
        "evidence_id": "funding-evidence-1",
        "sleeve_id": "sleeve-alpha",
        "market_symbol": "BTC-PERPETUAL",
        "window_start_ns": START,
        "window_end_ns": END,
        "events": [event(1, "0.02"), event(0, "-0.01"), event(2, "-0.005")],
    }
    values.update(overrides)
    return build_paper_sleeve_funding_evidence(**values)  # type: ignore[arg-type]


def verify(evidence: object) -> EdgeEvidenceVerification:
    return verify_paper_sleeve_funding_evidence(evidence)


def _reseal(evidence: PaperSleeveFundingEvidence, **changes: object) -> PaperSleeveFundingEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, funding_evidence_digest=paper_sleeve_funding_evidence_digest(changed))


def _corrupted(**changes: object) -> PaperSleeveFundingEvidence:
    copy = replace(build())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


def test_events_are_canonically_ordered_and_the_total_is_exact() -> None:
    evidence = build()
    assert [item.event_id for item in evidence.events] == ["funding-0", "funding-1", "funding-2"]
    assert evidence.event_count == 3
    assert Fraction(evidence.funding_total) == Fraction("-0.01") + Fraction("0.02") + Fraction("-0.005")
    assert evidence.funding_total == d("0.005")
    assert verify(evidence).intact is True


def test_insertion_order_does_not_change_the_evidence() -> None:
    forward = build(events=[event(0), event(1), event(2)])
    backward = build(events=(event(2), event(1), event(0)))
    assert forward == backward
    assert forward.funding_evidence_digest == backward.funding_evidence_digest


def test_empty_events_are_an_explicit_digest_bound_statement() -> None:
    evidence = build(events=[])
    assert evidence.events == ()
    assert evidence.event_count == 0
    assert evidence.funding_total == d("0")
    assert verify(evidence).intact is True


def test_window_boundaries_follow_start_inclusive_end_exclusive() -> None:
    first = build(events=[event(0, settlement_at_ns=START)])
    assert first.events[0].settlement_at_ns == START
    with _raises("settlement_outside_window"):
        build(events=[event(0, settlement_at_ns=END)])
    with _raises("settlement_outside_window"):
        build(events=[event(0, settlement_at_ns=START - 1)])


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"window_start_ns": START + 1}, "window_not_utc_day_aligned"),
        ({"window_end_ns": START}, "window_not_utc_day_aligned"),
        ({"window_end_ns": END + 1}, "window_not_utc_day_aligned"),
        ({"window_start_ns": True}, "window_start_ns_invalid"),
        ({"window_start_ns": -DAY_NS}, "window_start_ns_invalid"),
        ({"window_end_ns": INT64_MAX + 1}, "window_end_ns_invalid"),
        ({"events": None}, "events_malformed"),
        ({"events": {event(0)}}, "events_malformed"),
        ({"events": [{"event_id": "funding-0"}]}, "event_malformed"),
        ({"events": [event(0), event(0, "-0.02")]}, "event_id_duplicate"),
        ({"events": [event(0), event(1, event_id="FUNDING-0")]}, "event_id_case_ambiguous"),
        ({"events": [event(0), event(1, settlement_at_ns=START + 8 * HOUR_NS)]}, "settlement_instant_duplicate"),
        ({"events": [event(0, position_state_digest="A" * 64)]}, "position_state_digest_invalid"),
        ({"events": [event(0, funding_amount="-0.01")]}, "funding_amount_invalid"),
        ({"events": [event(0, funding_amount=-0.01)]}, "funding_amount_invalid"),
        ({"events": [event(0, funding_amount="-" + d("0"))]}, "funding_amount_invalid"),
        ({"events": [event(0, funding_amount=_Text(d("-0.01")))]}, "funding_amount_invalid"),
        ({"events": [event(0, settlement_at_ns=True)]}, "settlement_at_ns_invalid"),
        ({"events": [event(0, event_id="funding 0")]}, "event_id_invalid"),
        ({"sleeve_id": "live"}, "forbidden_scope_token:sleeve_id"),
        ({"market_symbol": "BTC PERP"}, "market_symbol_invalid"),
        ({"evidence_id": ""}, "evidence_id_invalid"),
    ],
)
def test_malformed_funding_evidence_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    with _raises(code):
        build(**overrides)


def test_a_total_beyond_the_representation_bound_is_refused() -> None:
    largest = "9" * 41 + "." + "0" * 18
    with _raises("funding_total_not_representable"):
        build(events=[event(0, funding_amount=largest), event(1, funding_amount=largest)])


def test_rule_set_digest_commits_the_rule_set() -> None:
    rule_set = paper_sleeve_funding_evidence_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == PAPER_SLEEVE_FUNDING_EVIDENCE_RULE_SET_DIGEST
    assert build().rule_set_digest == PAPER_SLEEVE_FUNDING_EVIDENCE_RULE_SET_DIGEST
    assert "origin_not_proven" in str(rule_set["origin_rule_id"])


def test_payload_round_trips_and_digest_recomputes() -> None:
    evidence = build()
    payload = json.loads(json.dumps(paper_sleeve_funding_evidence_to_dict(evidence)))
    assert paper_sleeve_funding_evidence_payload_is_well_formed(payload) is True
    assert paper_sleeve_funding_evidence_from_payload(payload) == evidence
    assert paper_sleeve_funding_evidence_digest(evidence) == evidence.funding_evidence_digest


def test_stale_self_digest_and_resealed_mutations_are_rejected() -> None:
    evidence = build()
    stale = verify(replace(evidence, funding_evidence_digest="0" * 64))
    assert stale.intact is False
    assert _code("self_digest_mismatch") in stale.reason_codes
    forged_total = verify(_reseal(evidence, funding_total=d("0")))
    assert forged_total.intact is False
    assert _code("field_mismatch:funding_total") in forged_total.reason_codes
    reordered = verify(_reseal(evidence, events=tuple(reversed(evidence.events))))
    assert reordered.intact is False
    assert _code("field_mismatch:events") in reordered.reason_codes


@pytest.mark.parametrize(
    "artifact",
    [
        pytest.param(None, id="none"),
        pytest.param({}, id="dict"),
        pytest.param(object.__new__(PaperSleeveFundingEvidence), id="uninitialized"),
        pytest.param(_corrupted(events=[event(0)]), id="list_events"),
        pytest.param(_corrupted(event_count=True), id="bool_count"),
        pytest.param(_corrupted(funding_amount_origin_proven=True), id="forged_origin"),
        pytest.param(_corrupted(sleeve_id=_Text("sleeve-alpha")), id="text_subclass"),
        pytest.param(_corrupted(window_end_ns=10**5000), id="huge_int"),
    ],
)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify(artifact)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("events", 0, "funding_amount"), "-0.01"),
        (("events", 0, "settlement_at_ns"), "1"),
        (("event_count",), -1),
        (("funding_total",), 0.005),
        (("venue_funding_rate_consumed",), None),
    ],
    ids=lambda value: str(value)[:30],
)
def test_parser_refuses_states_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    payload = json.loads(json.dumps(paper_sleeve_funding_evidence_to_dict(build())))
    target: object = payload
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    assert paper_sleeve_funding_evidence_payload_is_well_formed(payload) is False


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flags = dict(PAPER_SLEEVE_FUNDING_EVIDENCE_NON_CLAIM_FLAGS)
    assert flags.pop("paper_only") is True
    assert set(flags.values()) == {False}
    origin_flags = {"funding_amount_origin_proven", "settlement_time_origin_proven", "venue_funding_rate_consumed"}
    assert origin_flags <= set(flags)
    all_flags = dict(PAPER_SLEEVE_FUNDING_EVIDENCE_NON_CLAIM_FLAGS)
    defaults = {item.name: item.default for item in fields(PaperSleeveFundingEvidence) if item.name in all_flags}
    assert defaults == all_flags
    assert not set(all_flags) & set(inspect.signature(build_paper_sleeve_funding_evidence).parameters)
    with pytest.raises(FrozenInstanceError):
        build().funding_total = d("0")  # type: ignore[misc]


def test_no_funding_value_or_rate_is_embedded_in_source() -> None:
    tree = ast.parse(Path(funding_module.__file__).read_text(encoding="utf-8"))
    constants = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)]
    numeric_text = re.compile(r"-?(?:[0-9]+\.[0-9]+|[0-9]{2,})")
    assert not [value for value in constants if type(value) is str and numeric_text.fullmatch(value)]
    assert {value for value in constants if type(value) is int} <= {
        0,
        1,
        10,
        18,
        32,
        60,
        64,
        127,
        128,
        256,
        86_400_000_000_000,
        INT64_MAX,
    }


def test_module_is_pure_and_consumes_only_the_edge_kernel() -> None:
    pit.assert_module_is_pure(funding_module, {"crypto_core.validation.edge_artifact_core"})


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    pit.assert_single_assembly_path(
        funding_module,
        "PaperSleeveFundingEvidence",
        "_assemble_evidence",
        "build_paper_sleeve_funding_evidence",
        "_reassemble_evidence",
    )


def test_public_api_is_exact() -> None:
    assert set(funding_module.__all__) == {
        "PAPER_SLEEVE_FUNDING_EVIDENCE_NON_CLAIM_FLAGS",
        "PAPER_SLEEVE_FUNDING_EVIDENCE_RULE_SET_DIGEST",
        "PaperSleeveFundingEvent",
        "PaperSleeveFundingEvidence",
        "PaperSleeveFundingEvidenceError",
        "build_paper_sleeve_funding_evidence",
        "paper_sleeve_funding_evidence_digest",
        "paper_sleeve_funding_evidence_from_payload",
        "paper_sleeve_funding_evidence_payload_is_well_formed",
        "paper_sleeve_funding_evidence_rule_set",
        "paper_sleeve_funding_evidence_to_dict",
        "verify_paper_sleeve_funding_evidence",
    }
