"""Canonical typed identity of the governed paper execution contract (TCI_V1).

Design authority: ``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 7, contract
``GOVERNED_PAPER_TYPED_PROVENANCE_V2``. Contract-local and schema-bounded: it serves only the governed paper execution
modules and is not a repository-wide serialization framework.

Python equality is never an identity proof. It collapses ``False == 0`` and ``True == 1``, it equates a str-backed
Enum member with its value, and a dataclass ``==`` inherits those collapses field by field. A TCI image encodes the
exact type of every node together with its value:

* ``None`` -> ``["none"]``; an exact ``bool`` -> ``["bool", v]``; an exact ``int`` (never a bool, within the signed
  64-bit range) -> ``["int", v]``; an exact ``str`` -> ``["str", v]``;
* an exact ``tuple`` or ``list`` -> ``["tuple", [...]]`` or ``["list", [...]]``; an exact ``dict`` whose keys are exact
  ``str`` -> ``["dict", [[key, image], ...]]`` in key order;
* a member of an approved Enum class -> ``["enum", name, image(value)]``. Enum members are dispatched by their exact
  class, so a str- or int-backed member never images like its underlying value;
* an instance of an approved dataclass -> ``["dataclass", name, [[field, image], ...]]`` over every declared field in
  declaration order;
* an instance of an approved REFERENCE class -> ``["ref", name, digest]``. The caller's resolver must first re-prove the
  value through its owning public verifier and return the independently recomputed digest; a reference is never taken
  on trust.

Everything else is refused: float, Fraction, Decimal, bytes, sets, subclasses of the primitives that are not approved
Enum members, and every foreign class. A class is approved by identity, never by its name. A
``GovernedPaperTypeDomain`` is the closure of explicit root schemas over their declared field annotations, keyed by
the class objects themselves; a field annotated with anything outside the supported forms fails the domain, and two
approved classes may not share a name, so a foreign class that copies a display name cannot pass.

The identity digest is SHA-256 over the canonical JSON of the image. The canonical WIRE serialization and the
self-digests of every artifact are unchanged: typed identity is an additional comparison and an additional lineage
binding, never a new wire format.

``governed_paper_verify_rebuilt`` is the one total verifier boundary of the contract's owned artifacts. It checks the
exact type, the typed image of the carried artifact, the carried self-digest against its recomputation over the wire
payload, and typed identity, field by field, against a rebuild through the artifact's single assembly path. It never
raises.
"""

from __future__ import annotations

import typing
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from enum import Enum

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceVerification,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_sha256_text,
)

_PREFIX = "governed_paper_typed_identity"
_MAX_INT = 9_223_372_036_854_775_807
_PRIMITIVES = (type(None), bool, int, str)

GOVERNED_PAPER_TYPED_IDENTITY_SCHEMA = "governed-paper-typed-image.v1"

Resolver = Callable[[object], str]


class GovernedPaperTypedIdentityError(EdgeArtifactError):
    """A value outside its approved domain, or a malformed domain: never an identity."""


def _fail(code: str) -> GovernedPaperTypedIdentityError:
    return GovernedPaperTypedIdentityError(f"{_PREFIX}:{code}")


def _class_name(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


class GovernedPaperTypeDomain:
    """An allowlisted, schema-bounded type domain: the closure of root schemas over their declared annotations."""

    def __init__(self, domain_id: str, *, roots: tuple[type, ...], references: tuple[type, ...] = ()) -> None:
        if type(domain_id) is not str or not domain_id:
            raise _fail("domain_id_invalid")
        if type(roots) is not tuple or not roots or type(references) is not tuple:
            raise _fail("domain_roots_invalid")
        self.domain_id = domain_id
        self._references: dict[type, str] = {}
        for cls in references:
            if not isinstance(cls, type):
                raise _fail("domain_reference_invalid")
            self._references[cls] = _class_name(cls)
        self._dataclasses: dict[type, str] = {}
        self._enums: dict[type, str] = {}
        for root in roots:
            if not (isinstance(root, type) and is_dataclass(root)) or root in self._references:
                raise _fail("domain_root_not_a_dataclass")
            self._visit(root)
        names = [*self._dataclasses.values(), *self._enums.values(), *self._references.values()]
        if len(set(names)) != len(names):
            raise _fail("domain_class_name_not_unique")

    def _visit(self, cls: type) -> None:
        if cls in self._dataclasses:
            return
        self._dataclasses[cls] = _class_name(cls)
        try:
            hints = typing.get_type_hints(cls)
        except Exception as exc:  # noqa: BLE001 - an unresolvable schema can never be an approved domain
            raise _fail(f"domain_annotation_unresolvable:{_class_name(cls)}") from exc
        for item in fields(cls):
            self._annotation(hints[item.name], f"{_class_name(cls)}.{item.name}")

    def _annotation(self, annotation: object, owner: str) -> None:
        if typing.get_origin(annotation) in (typing.Union, tuple, list, dict, type(int | None)):
            for argument in typing.get_args(annotation):
                if argument is not Ellipsis:
                    self._annotation(argument, owner)
            return
        if annotation in _PRIMITIVES or annotation in self._references:
            return
        if isinstance(annotation, type) and is_dataclass(annotation):
            self._visit(annotation)
            return
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            self._enums[annotation] = _class_name(annotation)
            return
        raise _fail(f"domain_annotation_unsupported:{owner}")

    @property
    def class_names(self) -> tuple[str, ...]:
        """Every approved name (dataclasses, Enums and references), sorted."""

        return tuple(sorted([*self._dataclasses.values(), *self._enums.values(), *self._references.values()]))

    def image(self, value: object, resolve: Mapping[type, Resolver] | None = None) -> object:
        """The typed image of ``value`` in this domain; raises ``GovernedPaperTypedIdentityError`` outside it."""

        kind = type(value)
        if value is None:
            return ["none"]
        if kind is bool:
            return ["bool", value]
        if kind is int:
            if not -_MAX_INT <= value <= _MAX_INT:  # type: ignore[operator]
                raise _fail("int_out_of_range")
            return ["int", value]
        if kind is str:
            return ["str", value]
        if kind is tuple or kind is list:
            return ["tuple" if kind is tuple else "list", [self.image(item, resolve) for item in value]]  # type: ignore[attr-defined]
        if kind is dict:
            if any(type(key) is not str for key in value):  # type: ignore[attr-defined]
                raise _fail("dict_key_not_exact_str")
            return ["dict", [[key, self.image(value[key], resolve)] for key in sorted(value)]]  # type: ignore[index,call-overload]
        name = self._enums.get(kind)
        if name is not None:
            return ["enum", name, self.image(value.value, resolve)]  # type: ignore[attr-defined]
        name = self._dataclasses.get(kind)
        if name is not None:
            return [
                "dataclass",
                name,
                [[item.name, self.image(getattr(value, item.name), resolve)] for item in fields(kind)],  # type: ignore[arg-type]
            ]
        name = self._references.get(kind)
        if name is not None:
            resolver = None if resolve is None else resolve.get(kind)
            if resolver is None:
                raise _fail(f"reference_unresolved:{name}")
            digest = resolver(value)
            if not edge_is_hex64(digest):
                raise _fail(f"reference_digest_invalid:{name}")
            return ["ref", name, digest]
        raise _fail(f"type_not_in_domain:{_class_name(kind)}")


def governed_paper_typed_image(
    value: object, domain: GovernedPaperTypeDomain, *, resolve: Mapping[type, Resolver] | None = None
) -> object:
    """The typed image of ``value`` (see the module docstring); raises outside the domain."""

    if type(domain) is not GovernedPaperTypeDomain:
        raise _fail("domain_malformed")
    return domain.image(value, resolve)


def governed_paper_typed_identity_digest(
    value: object, domain: GovernedPaperTypeDomain, *, resolve: Mapping[type, Resolver] | None = None
) -> str:
    """SHA-256 of the canonical JSON of the typed image; raises outside the domain."""

    return edge_sha256_text(edge_canonical_json(governed_paper_typed_image(value, domain, resolve=resolve)))


def governed_paper_typed_identical(
    left: object, right: object, domain: GovernedPaperTypeDomain, *, resolve: Mapping[type, Resolver] | None = None
) -> bool:
    """Exact typed identity of two values; raises when either lies outside the domain."""

    image = governed_paper_typed_image
    return edge_canonical_json(image(left, domain, resolve=resolve)) == edge_canonical_json(
        image(right, domain, resolve=resolve)
    )


def governed_paper_verify_rebuilt(
    artifact: object,
    *,
    cls: type,
    domain: GovernedPaperTypeDomain,
    to_payload: Callable[[object], dict],
    digest_field: str,
    rebuild: Callable[[], object],
    code: str,
    reason: Callable[[str], str],
    resolve: Mapping[type, Resolver] | None = None,
) -> EdgeEvidenceVerification:
    """The total typed verifier of one owned artifact: never raises, for any objects.

    Stages, each failing closed with its own reason: exact type -> typed image of the carried artifact -> wire
    payload and self-digest recomputation -> rebuild through the single assembly path -> typed identity field by field.
    """

    stage = f"{code}_type_invalid"
    try:
        if type(artifact) is not cls:
            return EdgeEvidenceVerification(False, (reason(stage),), "", "")
        stage = f"{code}_not_canonically_typed"
        carried = domain.image(artifact, resolve)
        stage = f"{code}_serialization_failed"
        payload = to_payload(artifact)
        canonical = edge_canonical_json(payload)
        recomputed = edge_payload_digest(payload, digest_field)
        stage = f"{code}_rebuild_failed"
        rebuilt = rebuild()
        if type(rebuilt) is not cls:
            return EdgeEvidenceVerification(False, (reason(stage),), "", "")
        expected = domain.image(rebuilt, resolve)
        codes: set[str] = set()
        if payload[digest_field] != recomputed:
            codes.add(reason(f"{code}_self_digest_mismatch"))
        for (name, carried_value), (_, expected_value) in zip(carried[2], expected[2], strict=True):  # type: ignore[index]
            if edge_canonical_json(carried_value) != edge_canonical_json(expected_value):
                codes.add(reason(f"{code}_field_mismatch:{name}"))
        reason_codes = tuple(sorted(codes))
        return EdgeEvidenceVerification(
            intact=not reason_codes, reason_codes=reason_codes, recomputed_digest=recomputed, canonical_json=canonical
        )
    except Exception:  # noqa: BLE001 - VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT
        return EdgeEvidenceVerification(False, (reason(stage),), "", "")


__all__ = [
    "GOVERNED_PAPER_TYPED_IDENTITY_SCHEMA",
    "GovernedPaperTypeDomain",
    "GovernedPaperTypedIdentityError",
    "governed_paper_typed_identical",
    "governed_paper_typed_identity_digest",
    "governed_paper_typed_image",
    "governed_paper_verify_rebuilt",
]
