"""Canonical typed identity (TCI_V1) tests of the governed paper execution contract (GOVERNED_PAPER_TYPED_PROVENANCE_V2).

Python equality is never an identity proof: ``False == 0``, ``True == 1`` and a str-backed Enum member equals its value.
These tests pin that a typed image distinguishes every such pair, refuses every unsupported leaf and every foreign
class, and that the one total verifier boundary never raises. Pure and fast: no world is built here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum, IntEnum
from fractions import Fraction
from typing import Any

import pytest

from crypto_core.validation.edge_artifact_core import edge_canonical_json, edge_payload_digest, edge_sha256_text
from crypto_core.validation.governed_paper_typed_identity import (
    GOVERNED_PAPER_TYPED_IDENTITY_SCHEMA,
    GovernedPaperTypedIdentityError,
    GovernedPaperTypeDomain,
    governed_paper_typed_identical,
    governed_paper_typed_identity_digest,
    governed_paper_typed_image,
    governed_paper_verify_rebuilt,
)

_PREFIX = "governed_paper_typed_identity"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Level(IntEnum):
    ONE = 1
    TWO = 2


@dataclass(frozen=True)
class Leg:
    side: Side
    level: Level
    units: str


@dataclass(frozen=True)
class Record:
    """A schema that exercises every supported annotation form."""

    flag: bool
    count: int
    name: str
    note: str | None
    legs: tuple[Leg, ...]
    tags: list[str]
    labels: dict[str, str]
    pairs: tuple[tuple[str, int], ...]
    digest: str


@dataclass(frozen=True)
class Opaque:
    """A reference class: imaged only as its resolver's digest."""

    payload: str


@dataclass(frozen=True)
class Holder:
    reference: Opaque
    flag: bool


class Text(str):
    pass


class Number(int):
    pass


def make_record(**changes: object) -> Record:
    values: dict[str, object] = {
        "flag": True,
        "count": 1,
        "name": "record-1",
        "note": None,
        "legs": (Leg(Side.BUY, Level.ONE, "1"),),
        "tags": ["a", "b"],
        "labels": {"b": "2", "a": "1"},
        "pairs": (("x", 0),),
        "digest": "",
    }
    values.update(changes)
    return Record(**values)  # type: ignore[arg-type]


DOMAIN = GovernedPaperTypeDomain("tci-test-record.v1", roots=(Record,))
HOLDER = GovernedPaperTypeDomain("tci-test-holder.v1", roots=(Holder,), references=(Opaque,))


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def refused(text: str):  # noqa: ANN201
    return pytest.raises(GovernedPaperTypedIdentityError, match=f"^{re.escape(code(text))}$")


def digest(value: object, domain: GovernedPaperTypeDomain = DOMAIN) -> str:
    return governed_paper_typed_identity_digest(value, domain)


# --- the image distinguishes what Python equality collapses ---------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (False, 0),
        (True, 1),
        (Side.BUY, "BUY"),
        (Level.ONE, 1),
        ((1, 2), [1, 2]),
        (None, "None"),
        ("1", 1),
    ],
)
def test_python_equality_is_never_typed_identity(left: object, right: object) -> None:
    if isinstance(left, Enum) or isinstance(right, Enum):
        domain = GovernedPaperTypeDomain("tci-test-enums.v1", roots=(Leg,))
    else:
        domain = DOMAIN
    assert governed_paper_typed_identical(left, left, domain)
    assert not governed_paper_typed_identical(left, right, domain)
    assert digest(left, domain) != digest(right, domain)


def test_a_nested_bool_int_substitution_changes_the_identity() -> None:
    record = make_record()
    assert record == make_record(flag=1, legs=(Leg(Side.BUY, Level.ONE, "1"),))  # Python equality collapses both
    for forged in (
        make_record(flag=1),
        make_record(count=True),
        make_record(pairs=(("x", False),)),
        make_record(legs=(Leg("BUY", Level.ONE, "1"),)),  # type: ignore[arg-type]
        make_record(legs=(Leg(Side.BUY, 1, "1"),)),  # type: ignore[arg-type]
        make_record(tags=("a", "b")),
    ):
        assert not governed_paper_typed_identical(record, forged, DOMAIN)


def test_the_image_records_the_exact_type_and_value_of_every_node() -> None:
    image = governed_paper_typed_image(make_record(), DOMAIN)
    name = f"{Record.__module__}.{Record.__qualname__}"
    assert image[0:2] == ["dataclass", name]
    fields = dict(image[2])  # type: ignore[arg-type]
    assert fields["flag"] == ["bool", True] and fields["count"] == ["int", 1] and fields["note"] == ["none"]
    assert fields["tags"] == ["list", [["str", "a"], ["str", "b"]]]
    assert fields["labels"] == ["dict", [["a", ["str", "1"]], ["b", ["str", "2"]]]]
    leg = fields["legs"][1][0]  # type: ignore[index]
    assert leg[2][0] == ["side", ["enum", f"{Side.__module__}.{Side.__qualname__}", ["str", "BUY"]]]
    assert leg[2][1] == ["level", ["enum", f"{Level.__module__}.{Level.__qualname__}", ["int", 1]]]


def test_the_identity_digest_is_deterministic_and_is_the_hash_of_the_canonical_image() -> None:
    record = make_record()
    assert digest(record) == digest(make_record()) == digest(record)
    assert digest(record) == edge_sha256_text(edge_canonical_json(governed_paper_typed_image(record, DOMAIN)))
    assert digest(make_record(labels={"a": "1", "b": "2"})) == digest(record)  # key order is canonical
    assert GOVERNED_PAPER_TYPED_IDENTITY_SCHEMA == "governed-paper-typed-image.v1"


# --- unsupported leaves, subclasses and foreign classes are refused, never converted ---------------------------------------


@pytest.mark.parametrize(
    "value",
    [1.0, Fraction(1, 2), Decimal("1"), b"x", {"a"}, frozenset({"a"}), object(), Text("x"), Number(1)],
)
def test_unsupported_leaves_and_primitive_subclasses_are_refused(value: object) -> None:
    with pytest.raises(GovernedPaperTypedIdentityError, match=f"^{re.escape(code('type_not_in_domain:'))}"):
        governed_paper_typed_image(value, DOMAIN)
    with pytest.raises(GovernedPaperTypedIdentityError):
        governed_paper_typed_image(make_record(name=value), DOMAIN)


def test_a_foreign_class_with_the_same_display_name_is_refused() -> None:
    Spoof = type("Record", (), {"__module__": Record.__module__, "__qualname__": Record.__qualname__})  # noqa: N806
    with refused(f"type_not_in_domain:{Record.__module__}.{Record.__qualname__}"):
        governed_paper_typed_image(Spoof(), DOMAIN)

    @dataclass(frozen=True)
    class ForeignLeg:
        side: Side
        level: Level
        units: str

    ForeignLeg.__module__, ForeignLeg.__qualname__ = Leg.__module__, Leg.__qualname__  # copies the approved name

    foreign = ForeignLeg(Side.BUY, Level.ONE, "1")
    with pytest.raises(GovernedPaperTypedIdentityError):
        governed_paper_typed_image(make_record(legs=(foreign,)), DOMAIN)


def test_out_of_range_integers_and_non_string_keys_are_refused() -> None:
    with refused("int_out_of_range"):
        governed_paper_typed_image(make_record(count=2**63), DOMAIN)
    with refused("dict_key_not_exact_str"):
        governed_paper_typed_image(make_record(labels={1: "x"}), DOMAIN)
    with refused("dict_key_not_exact_str"):
        governed_paper_typed_image(make_record(labels={Text("a"): "x"}), DOMAIN)


# --- references are re-proven by their resolver, never taken on trust -------------------------------------------------------


def test_a_reference_is_imaged_only_as_its_resolved_digest() -> None:
    holder = Holder(Opaque("payload"), True)
    with refused(f"reference_unresolved:{Opaque.__module__}.{Opaque.__qualname__}"):
        governed_paper_typed_image(holder, HOLDER)
    with refused(f"reference_digest_invalid:{Opaque.__module__}.{Opaque.__qualname__}"):
        governed_paper_typed_image(holder, HOLDER, resolve={Opaque: lambda value: "not-a-digest"})
    resolved = governed_paper_typed_image(holder, HOLDER, resolve={Opaque: lambda value: "a" * 64})
    assert dict(resolved[2])["reference"] == ["ref", f"{Opaque.__module__}.{Opaque.__qualname__}", "a" * 64]  # type: ignore[index]
    with pytest.raises(GovernedPaperTypedIdentityError):
        governed_paper_typed_image(Opaque("payload"), DOMAIN)


# --- the domain is schema-bounded ----------------------------------------------------------------------------------------


def test_a_domain_is_the_closure_of_its_root_schemas_only() -> None:
    names = DOMAIN.class_names
    assert names == tuple(sorted(names))
    assert {name.rsplit(".", 1)[-1] for name in names} == {"Record", "Leg", "Side", "Level"}

    @dataclass(frozen=True)
    class Floaty:
        value: float

    @dataclass(frozen=True)
    class Open:
        value: dict[str, Any]

    for root in (Floaty, Open):
        with pytest.raises(GovernedPaperTypedIdentityError, match="domain_annotation_unsupported"):
            GovernedPaperTypeDomain("tci-test-bad.v1", roots=(root,))
    with refused("domain_root_not_a_dataclass"):
        GovernedPaperTypeDomain("tci-test-bad.v1", roots=(Side,))
    with refused("domain_roots_invalid"):
        GovernedPaperTypeDomain("tci-test-bad.v1", roots=())
    with refused("domain_id_invalid"):
        GovernedPaperTypeDomain("", roots=(Record,))
    with refused("domain_malformed"):
        governed_paper_typed_image(make_record(), object())  # type: ignore[arg-type]


def test_two_approved_classes_may_never_share_a_name() -> None:
    first = Enum("Twin", ["A"], module="tci.twins", qualname="Twin")
    second = Enum("Twin", ["B"], module="tci.twins", qualname="Twin")
    assert first is not second
    roots = []
    for index, enum in enumerate((first, second)):
        roots.append(dataclass(frozen=True)(type(f"Root{index}", (), {"__annotations__": {"value": enum}})))
    with refused("domain_class_name_not_unique"):
        GovernedPaperTypeDomain("tci-test-twins.v1", roots=tuple(roots))


# --- the one total verifier boundary ---------------------------------------------------------------------------------------


def _seal(record: Record) -> Record:
    return replace(record, digest=edge_payload_digest(_payload(record), "digest"))


def _wire(value: object) -> object:
    """The wire form of one leaf: an Enum member serializes as its value, exactly like the contract's serializers."""

    return value.value if isinstance(value, Enum) else value


def _payload(record: object) -> dict:
    return {
        "flag": record.flag,  # type: ignore[attr-defined]
        "count": record.count,  # type: ignore[attr-defined]
        "name": record.name,  # type: ignore[attr-defined]
        "note": record.note,  # type: ignore[attr-defined]
        "legs": [[_wire(leg.side), _wire(leg.level), leg.units] for leg in record.legs],  # type: ignore[attr-defined]
        "tags": list(record.tags),  # type: ignore[attr-defined]
        "labels": dict(record.labels),  # type: ignore[attr-defined]
        "pairs": [list(pair) for pair in record.pairs],  # type: ignore[attr-defined]
        "digest": record.digest,  # type: ignore[attr-defined]
    }


def verify(artifact: object, rebuild=None):  # noqa: ANN001, ANN201
    built = _seal(make_record())
    return governed_paper_verify_rebuilt(
        artifact,
        cls=Record,
        domain=DOMAIN,
        to_payload=_payload,
        digest_field="digest",
        rebuild=(lambda: built) if rebuild is None else rebuild,
        code="record",
        reason=lambda text: f"tci_test:{text}",
    )


def test_a_builder_output_verifies_intact() -> None:
    built = _seal(make_record())
    verification = verify(built)
    assert (verification.intact, verification.reason_codes, verification.recomputed_digest) == (True, (), built.digest)
    assert verification.canonical_json == edge_canonical_json(_payload(built))


@pytest.mark.parametrize(("name", "value"), [("flag", 1), ("count", True), ("name", "other")])
def test_a_substitution_never_verifies_whether_its_digest_is_retained_or_resealed(name: str, value: object) -> None:
    built = _seal(make_record())
    retained = replace(built, **{name: value})
    resealed = _seal(replace(make_record(), **{name: value}))
    for forged in (retained, resealed):
        verification = verify(forged)
        assert verification.intact is False
        assert f"tci_test:record_field_mismatch:{name}" in verification.reason_codes
    if name != "name":  # JSON already separates bool from int, so a retained digest no longer recomputes either
        assert "tci_test:record_self_digest_mismatch" in verify(retained).reason_codes


def test_a_str_enum_substitution_is_caught_although_its_json_is_identical() -> None:
    built = _seal(make_record())
    forged = _seal(replace(built, legs=(Leg("BUY", Level.ONE, "1"),)))  # type: ignore[arg-type]
    assert forged.digest == built.digest  # the wire payload cannot tell them apart
    verification = verify(forged)
    assert verification.intact is False and verification.reason_codes == ("tci_test:record_field_mismatch:legs",)


@pytest.mark.parametrize(
    ("artifact", "reason"),
    [
        (None, "tci_test:record_type_invalid"),
        (object(), "tci_test:record_type_invalid"),
        (Holder(Opaque("x"), True), "tci_test:record_type_invalid"),
        (make_record(count=1.5), "tci_test:record_not_canonically_typed"),
    ],
)
def test_the_verifier_is_total_and_reasons_are_deterministic(artifact: object, reason: str) -> None:
    verification = verify(artifact)
    assert (verification.intact, verification.reason_codes, verification.recomputed_digest) == (False, (reason,), "")


def test_a_failing_or_foreign_rebuild_never_verifies() -> None:
    built = _seal(make_record())

    def broken() -> object:
        raise RuntimeError("rebuild failed")

    for rebuild in (broken, lambda: Holder(Opaque("x"), True), lambda: object()):
        verification = verify(built, rebuild)
        assert verification.intact is False and verification.reason_codes == ("tci_test:record_rebuild_failed",)
