"""Roughtime draft-19 bounded REQUEST semantic decoder (internal MT-4 prerequisite K3) — provider-independent.

This module layers a pure, deterministic SEMANTIC view of one draft-19 REQUEST over the merged K1 structural
kernel (:mod:`crypto_core.validation.roughtime_v19_kernel`). K1 proves the draft-19 wire framing and the
generic tag/value message layout; K3 names the mandatory request tags, validates the known optional tags,
exposes exact typed values, preserves every undefined tag verbatim, and preserves the exact original request
bytes. It exists so later machine-time work can reason about a Roughtime request's declared content without
re-deriving the framing rules, building a request, or binding a provider, a key, a clock, or a nonce source.

Bounded profile (honest scope): this decoder implements ONE governance-selected, versioned semantic profile,
identified by :data:`ROUGHTIME_V19_REQUEST_SEMANTIC_PROFILE_ID`
(``"roughtime-v19-request-semantic-bounded-k3.v1"``). It inherits K1's structural bounds unchanged and adds
NO new byte-size ceilings of its own. An input that K1 rejects as OUTSIDE its bounded structural profile
(``profile_*`` reasons) is normalized here to :attr:`RoughtimeV19RequestSemanticReason.REQUEST_STRUCTURAL_INVALID`;
that means "outside the inherited K1 bounded profile or K1-malformed", NOT "malformed draft-19". No consumer
may convert a K3 structural rejection into a protocol-invalid claim.

Transport independence (deliberate): draft-19 discusses a minimum request size for UDP amplification control.
That is an ADVISORY TRANSPORT behaviour, not a parser validity rule, so this decoder imposes NO minimum
request or message size and accepts an otherwise-valid short request. A transport layer that needs a size
floor must enforce it separately; this module classifies no transport and sends nothing.

Request tag inventory (draft-19): the mandatory tags are ``VER``, ``NONC`` and ``TYPE``. The known optional
tags are ``SRV`` and ``ZZZZ``. ``PAD`` is NOT a draft-19 known padding field — an earlier draft used it, and
carrying that older meaning forward would be a semantic-leakage defect. A canonical ``PAD`` field is therefore
accepted as an ordinary UNKNOWN extension, preserved exactly, excluded from :attr:`padding`, and ignored
semantically.

Grease / unknown-tag policy (controller-mandated): undefined tags are NEVER rejected merely for being unknown.
Draft-19 requires implementations to ignore undefined tags. This decoder validates the known tags and their
values and preserves every remaining field as an exact, immutable K1
:class:`~crypto_core.validation.roughtime_v19_kernel.RoughtimeV19Field` in canonical wire order, exposed
through an ``extensions`` tuple with no invented semantics. K1 already rejects malformed, duplicate and
non-canonical tags structurally; K3 adds no second, contradictory duplicate-tag rule.

Request ``VER`` versus response ``VERS`` (asymmetric on purpose): the REQUEST ``VER`` list is non-empty, at
most 32 entries, and STRICTLY ASCENDING — repeated values are rejected. The merged K2 response ``VERS`` rule
is different (non-decreasing, duplicates accepted and preserved) and is left completely unchanged by this
module. Unknown version numbers are valid declared values; no specific version is required, and exposing a
version is never a claim that any provider deployed it.

Exact raw-byte binding: the exact original request packet bytes, the exact ``NONC`` bytes, the exact ``SRV``
bytes, the exact ``ZZZZ`` bytes and every extension value are preserved verbatim. Nothing is reconstructed
from decoded fields.

Scope boundary — what this decoder is NOT and never claims:

* it builds NO request, generates NO nonce, and uses NO randomness;
* it performs NO cryptography (no hashing of ``SRV``, no signature, no key object) and binds NO public key;
* it binds NO request to any response and correlates NO nonce;
* it binds NO provider or endpoint, resolves NO address, classifies NO transport, and infers NO deployed
  protocol version;
* it proves NO time and reads NO clock;
* it performs NO network, filesystem, environment, subprocess, or threading access;
* it reads or mutates NO other machine-time artifact (in particular no source registry) and builds no anchor
  evidence and no verification result;
* it has NO readiness or connector effect and triggers NO readiness or connector transition.

Trust boundary: :func:`parse_roughtime_v19_request` accepts exact built-in ``bytes`` only and rejects
``bytearray``, ``memoryview``, ``bytes`` subclasses and every other object before any other operation. All
structural work is delegated to the K1 public parser; every K1 failure and every domain failure is translated
to exactly one closed member of :class:`RoughtimeV19RequestSemanticReason`, so no raw
``RoughtimeV19KernelError``/``ValueError``/``IndexError``/``KeyError``/``TypeError``/``OverflowError`` and no
assertion failure is ever leaked, and no ``BaseException``/``KeyboardInterrupt``/``SystemExit``/
``GeneratorExit`` is caught. The public artifact is frozen and self-validates its own raw bytes through a
primitive semantic re-decode (never recursing through its public constructor), so a directly constructed
artifact can never represent decoded fields that differ from its exact raw bytes.

Versioned specification: https://datatracker.ietf.org/doc/html/draft-ietf-ntp-roughtime-19
Immutable official source snapshot reviewed: ietf-wg-ntp/draft-roughtime @
6157257b8ff618293e2ae379cf78e060fe975411 (described only as the immutable official source snapshot reviewed;
not asserted to be the exact publication-generation commit, and not proof of any provider's deployed version).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.roughtime_v19_kernel import (
    RoughtimeV19Field,
    RoughtimeV19KernelError,
    parse_roughtime_v19_packet,
)

# --- Semantic profile (governance-selected, versioned; inherits K1 structural bounds unchanged) -----------
ROUGHTIME_V19_REQUEST_SEMANTIC_PROFILE_ID = "roughtime-v19-request-semantic-bounded-k3.v1"

# --- Draft-19 request tag identities (exact four canonical bytes: 1-4 uppercase letters, then zero padding)
_TAG_VER = b"VER\x00"
_TAG_NONC = b"NONC"
_TAG_TYPE = b"TYPE"
_TAG_SRV = b"SRV\x00"
_TAG_ZZZZ = b"ZZZZ"

# Mandatory request tags; everything outside the KNOWN set below is a preserved extension.
_REQUEST_MANDATORY = frozenset({_TAG_VER, _TAG_NONC, _TAG_TYPE})
# Known tags are excluded from ``extensions`` because each is exposed as its own typed attribute. ``PAD`` is
# deliberately absent: it is not a draft-19 known padding field and must surface as an unknown extension.
_REQUEST_KNOWN = frozenset({_TAG_VER, _TAG_NONC, _TAG_TYPE, _TAG_SRV, _TAG_ZZZZ})

# --- Exact known-field lengths and pinned constants (bytes unless noted) ----------------------------------
_TAG_BYTES = 4  # every canonical tag is exactly four bytes
_UPPER_A = 0x41  # "A" — canonical-tag letter range (mirrors the K1 private rule; K1 helper is not importable)
_UPPER_Z = 0x5A  # "Z"
_NONC_BYTES = 32
_TYPE_BYTES = 4
_TYPE_VALUE = 0  # draft-19 request TYPE little-endian uint32 == 0
_SRV_BYTES = 32
_VER_ENTRY_BYTES = 4
_MAX_VER_ENTRIES = 32

# Sentinel for safe attribute inspection of exact-type objects that may have been built without their normal
# initializer (e.g. via object.__new__); identity comparison never triggers a caller-defined __eq__.
_MISSING = object()

# Fixed repository-owned messages for the closed error constructor.
_ERROR_REASON_TYPE_MESSAGE = "RoughtimeV19RequestSemanticError requires a RoughtimeV19RequestSemanticReason member"
_ERROR_IMMUTABLE_MESSAGE = "RoughtimeV19RequestSemanticError is immutable after construction"
_ERROR_LOCKED_ATTRS = frozenset({"reason", "_reason", "args"})


class RoughtimeV19RequestSemanticReason(str, Enum):
    """Closed, exact inventory of deterministic request-semantic reasons.

    Values are repository-standard lowercase identifiers; the member set is closed and never extended at
    runtime. ``REQUEST_STRUCTURAL_INVALID`` normalizes a K1 structural or K1 bounded-profile rejection; it
    means "outside the inherited K1 bounded profile or K1-malformed", never a claim about a provider's
    deployed protocol.
    """

    WRONG_INPUT_TYPE = "wrong_input_type"
    REQUEST_STRUCTURAL_INVALID = "request_structural_invalid"
    REQUEST_MISSING_MANDATORY_TAG = "request_missing_mandatory_tag"
    REQUEST_VER_INVALID = "request_ver_invalid"
    REQUEST_NONC_INVALID = "request_nonc_invalid"
    REQUEST_TYPE_INVALID = "request_type_invalid"
    REQUEST_SRV_INVALID = "request_srv_invalid"
    REQUEST_ZZZZ_INVALID = "request_zzzz_invalid"
    ARTIFACT_REQUEST_INCONSISTENT = "artifact_request_inconsistent"


class RoughtimeV19RequestSemanticError(RuntimeError):
    """Raised for every request-semantic failure, carrying exactly one closed reason.

    The constructor accepts ONLY an exact :class:`RoughtimeV19RequestSemanticReason` member. Any other
    argument raises a plain built-in ``TypeError`` before any attribute of the argument (in particular
    ``.value``) is read, so a hostile ``.value`` property or Enum-like substitute can never run. Once
    constructed the error is immutable: ``reason`` is read-only, its backing storage cannot be substituted,
    ``args`` cannot be replaced, and ``str(error)`` is always exactly ``reason.value``.
    """

    def __init__(self, reason: RoughtimeV19RequestSemanticReason) -> None:
        if type(reason) is not RoughtimeV19RequestSemanticReason:
            raise TypeError(_ERROR_REASON_TYPE_MESSAGE)
        object.__setattr__(self, "_reason", reason)
        super().__init__(reason.value)

    @property
    def reason(self) -> RoughtimeV19RequestSemanticReason:
        return self._reason

    def __setattr__(self, name: str, value: object) -> None:
        if name in _ERROR_LOCKED_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in _ERROR_LOCKED_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        super().__delattr__(name)


def _err(reason: RoughtimeV19RequestSemanticReason) -> RoughtimeV19RequestSemanticError:
    return RoughtimeV19RequestSemanticError(reason)


# --- Primitive semantic decoders (construct no public artifact; never recurse a public constructor) -------


def _tag_bytes_canonical(tag: bytes) -> bool:
    """Return whether ``tag`` (exactly four bytes) is a canonical draft-19 tag: 1-4 leading uppercase ASCII
    letters then zero padding. K1's private helper is not importable, so this mirrors its rule locally for
    safe validation of caller-supplied extension state; it never mutates or imports beyond K1's public API.
    """
    if not (_UPPER_A <= tag[0] <= _UPPER_Z):
        return False
    letters = 1
    while letters < _TAG_BYTES and _UPPER_A <= tag[letters] <= _UPPER_Z:
        letters += 1
    for index in range(letters, _TAG_BYTES):
        if tag[index] != 0:
            return False
    return True


def _decode_request_versions(ver_value: bytes) -> tuple[int, ...]:
    """Decode the REQUEST ``VER`` list into strictly ascending little-endian uint32 values.

    Non-empty, four-byte aligned, at most 32 entries, strictly ascending — a repeated value is REJECTED. This
    is deliberately stricter than the merged K2 response ``VERS`` rule (non-decreasing, duplicates preserved),
    which this module does not touch. No specific version is required and unknown version numbers are valid
    declared values; exposing a version asserts nothing about any deployment.

    The divisibility check is retained as defence in depth. For a ``VER`` field that is not last in canonical
    tag order, K1's four-byte offset alignment already forces a length divisible by four, so a non-divisible
    ``VER`` normally surfaces earlier as a K1 structural rejection.
    """
    length = len(ver_value)
    if length == 0:
        raise _err(RoughtimeV19RequestSemanticReason.REQUEST_VER_INVALID)
    if length % _VER_ENTRY_BYTES != 0:
        raise _err(RoughtimeV19RequestSemanticReason.REQUEST_VER_INVALID)
    count = length // _VER_ENTRY_BYTES
    if count > _MAX_VER_ENTRIES:
        raise _err(RoughtimeV19RequestSemanticReason.REQUEST_VER_INVALID)
    values = tuple(
        int.from_bytes(ver_value[index * _VER_ENTRY_BYTES : (index + 1) * _VER_ENTRY_BYTES], "little")
        for index in range(count)
    )
    for index in range(1, count):
        if values[index] <= values[index - 1]:  # rejects duplicates AND any descending relationship
            raise _err(RoughtimeV19RequestSemanticReason.REQUEST_VER_INVALID)
    return values


def _decode_request_primitive(
    packet_bytes: bytes,
) -> tuple[tuple[int, ...], bytes, int, bytes | None, bytes | None, tuple[RoughtimeV19Field, ...]]:
    """Decode one complete request packet; return the primitives needed to build the artifact.

    Order fixes deterministic error precedence: K1 structural parse, mandatory tag presence, ``VER``,
    ``NONC``, ``TYPE``, ``SRV``, ``ZZZZ``. Mandatory presence is checked against a pinned tuple rather than an
    unordered set so the selected reason never depends on iteration order.
    """
    try:
        packet = parse_roughtime_v19_packet(packet_bytes)
    except RoughtimeV19KernelError:
        raise _err(RoughtimeV19RequestSemanticReason.REQUEST_STRUCTURAL_INVALID) from None

    by_tag: dict[bytes, RoughtimeV19Field] = {}
    for field in packet.message.fields:
        by_tag[field.tag] = field
    for tag in (_TAG_VER, _TAG_NONC, _TAG_TYPE):  # pinned order; never set-iteration order
        if tag not in by_tag:
            raise _err(RoughtimeV19RequestSemanticReason.REQUEST_MISSING_MANDATORY_TAG)

    versions = _decode_request_versions(by_tag[_TAG_VER].value)

    nonce = by_tag[_TAG_NONC].value
    if len(nonce) != _NONC_BYTES:
        raise _err(RoughtimeV19RequestSemanticReason.REQUEST_NONC_INVALID)

    type_value = by_tag[_TAG_TYPE].value
    if len(type_value) != _TYPE_BYTES:
        raise _err(RoughtimeV19RequestSemanticReason.REQUEST_TYPE_INVALID)
    message_type = int.from_bytes(type_value, "little")
    if message_type != _TYPE_VALUE:
        raise _err(RoughtimeV19RequestSemanticReason.REQUEST_TYPE_INVALID)

    server_key_id: bytes | None = None
    if _TAG_SRV in by_tag:
        server_key_id = by_tag[_TAG_SRV].value
        if len(server_key_id) != _SRV_BYTES:
            raise _err(RoughtimeV19RequestSemanticReason.REQUEST_SRV_INVALID)

    padding: bytes | None = None
    if _TAG_ZZZZ in by_tag:
        padding = by_tag[_TAG_ZZZZ].value
        # Every padding byte must be zero. A zero-length present ZZZZ is valid and stays distinct from absent.
        if padding.count(0) != len(padding):
            raise _err(RoughtimeV19RequestSemanticReason.REQUEST_ZZZZ_INVALID)

    # K1 guarantees unique canonical tags in ascending wire order, so this preserves canonical order and
    # excludes exactly the known tags. A canonical PAD field is NOT known and therefore lands here.
    extensions = tuple(field for field in packet.message.fields if field.tag not in _REQUEST_KNOWN)
    return versions, nonce, message_type, server_key_id, padding, extensions


def _validate_extensions(
    supplied: object,
    decoded: tuple[RoughtimeV19Field, ...],
    reason: RoughtimeV19RequestSemanticReason,
) -> None:
    """Validate the COMPLETE state of every supplied extension before any comparison, then bind them to the
    K1-decoded extensions in canonical order.

    Exact class identity (``type(field) is RoughtimeV19Field``) does not prove the field's normal initializer
    ran, so each field's internal state is inspected safely: required attributes present (via ``getattr`` with
    a sentinel — never a caller ``__getattr__`` failure), exact built-in ``bytes`` tag / exact built-in ``int``
    ``tag_uint32`` / exact built-in ``bytes`` value, canonical four-byte tag, and ``tag_uint32`` equal to the
    tag's little-endian integer. Only after those exact-type gates is any value compared, so a hostile
    ``bytes``/``int`` subclass ``__eq__`` can never run first, and an incomplete field raises the closed
    ``reason`` rather than leaking ``AttributeError``.
    """
    if type(supplied) is not tuple:
        raise _err(reason)
    if len(supplied) != len(decoded):
        raise _err(reason)
    for index in range(len(supplied)):
        field = supplied[index]
        if type(field) is not RoughtimeV19Field:  # exact type; subclasses and forgeries rejected
            raise _err(reason)
        tag = getattr(field, "tag", _MISSING)
        tag_uint32 = getattr(field, "tag_uint32", _MISSING)
        value = getattr(field, "value", _MISSING)
        if tag is _MISSING or tag_uint32 is _MISSING or value is _MISSING:
            raise _err(reason)
        if type(tag) is not bytes or type(tag_uint32) is not int or type(value) is not bytes:
            raise _err(reason)
        if len(tag) != _TAG_BYTES or not _tag_bytes_canonical(tag):
            raise _err(reason)
        if tag_uint32 != int.from_bytes(tag, "little"):
            raise _err(reason)
        expected = decoded[index]  # trusted K1-decoded field (exact type, canonical, complete)
        if tag != expected.tag or tag_uint32 != expected.tag_uint32 or value != expected.value:
            raise _err(reason)


def _validate_optional_bytes(
    supplied: object,
    decoded: bytes | None,
    reason: RoughtimeV19RequestSemanticReason,
) -> None:
    """Bind an optional exact-``bytes``-or-``None`` field, keeping absent (``None``) distinct from present-empty
    (``b""``). ``None`` is admitted only when the re-decode also produced ``None``.
    """
    if supplied is None or decoded is None:
        if supplied is not None or decoded is not None:
            raise _err(reason)
        return
    if type(supplied) is not bytes:
        raise _err(reason)
    if supplied != decoded:
        raise _err(reason)


def _validate_request_state(obj: object, reason: RoughtimeV19RequestSemanticReason) -> None:
    """Prove an exact-type request object's COMPLETE current state matches the primitive re-decode of its own
    exact ``raw`` bytes.

    Reading state with ``getattr`` + a sentinel and applying exact-type gates before any value comparison means
    an object built without its initializer, an object mutated afterwards, or a wrong internal type raises
    ``reason`` and never leaks ``AttributeError``/``TypeError``/etc.
    """
    raw = getattr(obj, "raw", _MISSING)
    if raw is _MISSING or type(raw) is not bytes:
        raise _err(reason)
    try:
        versions, nonce, message_type, server_key_id, padding, extensions = _decode_request_primitive(raw)
    except RoughtimeV19RequestSemanticError:
        raise _err(reason) from None

    obj_versions = getattr(obj, "versions", _MISSING)
    obj_nonce = getattr(obj, "nonce", _MISSING)
    obj_type = getattr(obj, "message_type", _MISSING)
    obj_srv = getattr(obj, "server_key_id", _MISSING)
    obj_padding = getattr(obj, "padding", _MISSING)
    obj_ext = getattr(obj, "extensions", _MISSING)
    if (
        obj_versions is _MISSING
        or obj_nonce is _MISSING
        or obj_type is _MISSING
        or obj_srv is _MISSING
        or obj_padding is _MISSING
        or obj_ext is _MISSING
    ):
        raise _err(reason)

    if type(obj_versions) is not tuple:
        raise _err(reason)
    for entry in obj_versions:
        if type(entry) is not int:  # exact int per version entry; bool and int subclasses rejected
            raise _err(reason)
    if type(obj_nonce) is not bytes or type(obj_type) is not int:  # exact int; bool rejected
        raise _err(reason)
    if obj_versions != versions or obj_nonce != nonce or obj_type != message_type:
        raise _err(reason)
    _validate_optional_bytes(obj_srv, server_key_id, reason)
    _validate_optional_bytes(obj_padding, padding, reason)
    _validate_extensions(obj_ext, extensions, reason)


# --- Immutable, self-validating public artifact -----------------------------------------------------------


@dataclass(frozen=True)
class RoughtimeV19RequestSemantics:
    """Complete Roughtime draft-19 request semantics, self-validating on direct construction.

    Carries the strictly ascending ``versions`` tuple (uint32; exposed only, never asserted deployed), the
    exact 32-byte ``nonce`` (never generated here and never response-bound), the ``message_type`` (uint32
    == 0), the optional exact 32-byte ``server_key_id`` from ``SRV`` (never hashed, never provider-bound), the
    optional all-zero ``padding`` from ``ZZZZ`` (absent ``None`` stays distinct from present-empty ``b""``),
    every preserved unknown ``extensions`` field in canonical wire order (a canonical ``PAD`` field lands here,
    never in ``padding``), and the exact original request packet ``raw`` bytes.

    Direct construction re-decodes ``raw`` and requires every declared field to equal that primitive re-decode;
    any mismatch, missing/incomplete state, non-exact-type, forged/subclassed component, malformed raw, or
    object built without its initializer raises ``artifact_request_inconsistent`` (never a leaked
    ``AttributeError``).
    """

    versions: tuple[int, ...]
    nonce: bytes
    message_type: int
    server_key_id: bytes | None
    padding: bytes | None
    extensions: tuple[RoughtimeV19Field, ...]
    raw: bytes

    def __post_init__(self) -> None:
        _validate_request_state(self, RoughtimeV19RequestSemanticReason.ARTIFACT_REQUEST_INCONSISTENT)


def parse_roughtime_v19_request(packet_bytes: bytes) -> RoughtimeV19RequestSemantics:
    """Parse and semantically validate a Roughtime draft-19 request within the inherited K1 bounded profile.

    Accepts exact built-in ``bytes`` only. Delegates all structural work to the K1 public parser, validates the
    mandatory ``VER``/``NONC``/``TYPE`` tags and the known optional ``SRV``/``ZZZZ`` tags, preserves every
    unknown tag (including a canonical ``PAD``) as an extension, preserves the exact request bytes, and returns
    an immutable :class:`RoughtimeV19RequestSemantics`. Imposes no minimum request size, builds no request,
    uses no randomness, performs no cryptography, binds no provider, reads no clock, and causes no readiness or
    connector transition.
    """
    if type(packet_bytes) is not bytes:
        raise _err(RoughtimeV19RequestSemanticReason.WRONG_INPUT_TYPE)
    versions, nonce, message_type, server_key_id, padding, extensions = _decode_request_primitive(packet_bytes)
    return RoughtimeV19RequestSemantics(
        versions=versions,
        nonce=nonce,
        message_type=message_type,
        server_key_id=server_key_id,
        padding=padding,
        extensions=extensions,
        raw=packet_bytes,
    )


__all__ = [
    "ROUGHTIME_V19_REQUEST_SEMANTIC_PROFILE_ID",
    "RoughtimeV19RequestSemanticError",
    "RoughtimeV19RequestSemanticReason",
    "RoughtimeV19RequestSemantics",
    "parse_roughtime_v19_request",
]
