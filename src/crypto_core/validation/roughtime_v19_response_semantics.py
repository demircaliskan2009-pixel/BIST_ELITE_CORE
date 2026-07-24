"""Roughtime draft-19 bounded RESPONSE semantic decoder (internal MT-4 prerequisite K2) — provider-independent.

This module layers a pure, deterministic SEMANTIC view over the merged K1 structural kernel
(:mod:`crypto_core.validation.roughtime_v19_kernel`). K1 proves the draft-19 wire framing and the generic
tag/value message layout; K2 interprets one draft-19 RESPONSE: it names the mandatory outer tags, decodes the
nested SREP, CERT and DELE Roughtime messages through the K1 public parser, exposes exact typed values, and
preserves the exact raw bytes that a future signature-verification step will need. K2 performs no
cryptography. It exists so later machine-time work can reason about a Roughtime response's structure without
re-deriving the framing rules or prematurely binding a provider, a key, a clock, or a verification result.

Bounded profile (honest scope): this decoder implements ONE governance-selected, versioned semantic profile,
identified by :data:`ROUGHTIME_V19_RESPONSE_SEMANTIC_PROFILE_ID`
(``"roughtime-v19-response-semantic-bounded-k2.v1"``). It inherits K1's structural bounds unchanged and adds
NO new byte-size ceilings of its own. An input that K1 rejects as OUTSIDE its bounded structural profile
(``profile_*`` reasons) is normalized here to one closed K2 structural reason; that means "outside the
inherited K1 bounded profile", NOT "malformed draft-19". No consumer may convert a K2 structural rejection
into a protocol-invalid claim.

Grease / unknown-tag policy (controller-mandated): undefined tags are NEVER rejected merely for being
unknown. Draft-19 requires clients to ignore undefined tags. At every semantic level this decoder validates
the mandatory known tags and their values, and preserves every remaining field as an exact, immutable K1
:class:`~crypto_core.validation.roughtime_v19_kernel.RoughtimeV19Field` in canonical wire order, exposed
through an ``extensions`` tuple with no invented semantics. K1 already rejects malformed, duplicate and
non-canonical tags structurally; K2 adds no second, contradictory duplicate-tag rule.

Exact raw-byte binding: the exact outer packet bytes, the exact SREP value bytes, the exact CERT value bytes,
the exact nested DELE value bytes, both SIG values, NONC, each PATH node, ROOT, PUBK and every extension value
are preserved verbatim. Signed bytes are never reconstructed from decoded fields; a future signature check
consumes the original exact SREP and DELE values.

Scope boundary — what this decoder is NOT and never claims:

* it performs NO cryptography (no SHA-512, no Ed25519, no signature context, no key object);
* it verifies NO Merkle inclusion and interprets neither PATH nor INDX as a proof;
* it binds NO nonce to any request and constructs/parses no request;
* it binds NO provider, endpoint, or public key and infers NO deployed-protocol provenance
  (in particular it never claims Cloudflare or any provider compatibility, and the selected SREP ``VER`` is
  exposed as an exact integer only, never asserted to be an operationally admitted version);
* it proves NO time: MIDP/MINT/MAXT/RADI are exposed as exact integers, never converted to a wall clock or a
  datetime, and no clock is read;
* it admits NO machine-time origin and builds NO ``MachineTimeAnchorEvidence`` and no verification-result
  artifact, satisfies NO quorum, and reads or mutates NO source registry;
* it performs NO network, filesystem, environment, randomness, subprocess, or threading access;
* it has NO readiness or connector effect and triggers NO readiness or connector transition.

The non-cryptographic interval consistency it does check (``MINT <= MAXT`` inside DELE, and
``MINT <= MIDP <= MAXT`` across SREP and DELE) is a structural sanity constraint only; passing it does NOT
make the response cryptographically valid or its time authenticated.

Trust boundary: :func:`parse_roughtime_v19_response` accepts exact built-in ``bytes`` only. All structural
work is delegated to the K1 public parser; every K1 failure and every domain failure is translated to exactly
one closed member of :class:`RoughtimeV19ResponseSemanticReason`, so no raw
``RoughtimeV19KernelError``/``ValueError``/``IndexError``/``TypeError``/``OverflowError`` and no assertion
failure is ever leaked, and no ``BaseException`` is caught. The public artifacts are frozen and self-validate
their own raw bytes through a primitive semantic re-decode (never recursing through their public
constructors), so a directly constructed artifact can never represent decoded fields that differ from its
exact raw bytes.

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
    parse_roughtime_v19_message,
    parse_roughtime_v19_packet,
)

# --- Semantic profile (governance-selected, versioned; inherits K1 structural bounds unchanged) -----------
ROUGHTIME_V19_RESPONSE_SEMANTIC_PROFILE_ID = "roughtime-v19-response-semantic-bounded-k2.v1"

# --- Draft-19 tag identities (exact four canonical bytes: 1-4 uppercase letters, then zero padding) -------
_TAG_SIG = b"SIG\x00"
_TAG_NONC = b"NONC"
_TAG_TYPE = b"TYPE"
_TAG_PATH = b"PATH"
_TAG_SREP = b"SREP"
_TAG_CERT = b"CERT"
_TAG_INDX = b"INDX"
_TAG_VER = b"VER\x00"
_TAG_RADI = b"RADI"
_TAG_MIDP = b"MIDP"
_TAG_VERS = b"VERS"
_TAG_ROOT = b"ROOT"
_TAG_DELE = b"DELE"
_TAG_PUBK = b"PUBK"
_TAG_MINT = b"MINT"
_TAG_MAXT = b"MAXT"

# Mandatory known-tag sets per semantic level (everything else at that level is a preserved extension).
_OUTER_MANDATORY = frozenset({_TAG_SIG, _TAG_NONC, _TAG_TYPE, _TAG_PATH, _TAG_SREP, _TAG_CERT, _TAG_INDX})
_SREP_MANDATORY = frozenset({_TAG_VER, _TAG_RADI, _TAG_MIDP, _TAG_VERS, _TAG_ROOT})
_CERT_MANDATORY = frozenset({_TAG_SIG, _TAG_DELE})
_DELE_MANDATORY = frozenset({_TAG_PUBK, _TAG_MINT, _TAG_MAXT})

# --- Exact known-field lengths and pinned constants (bytes unless noted) ----------------------------------
_TAG_BYTES = 4  # every canonical tag is exactly four bytes
_UPPER_A = 0x41  # "A" — canonical-tag letter range (mirrors the K1 private rule; K1 helper is not importable)
_UPPER_Z = 0x5A  # "Z"
_SIG_BYTES = 64
_NONC_BYTES = 32
_TYPE_BYTES = 4
_TYPE_VALUE = 1  # draft-19 response TYPE little-endian uint32 == 1
_INDX_BYTES = 4
_VER_BYTES = 4
_RADI_BYTES = 4
_MIDP_BYTES = 8
_ROOT_BYTES = 32
_PUBK_BYTES = 32
_MINT_BYTES = 8
_MAXT_BYTES = 8
_PATH_NODE_BYTES = 32
_MAX_PATH_NODES = 32
_VERS_ENTRY_BYTES = 4

# Sentinel for safe attribute inspection of exact-type objects that may have been built without their normal
# initializer (e.g. via object.__new__); identity comparison never triggers a caller-defined __eq__.
_MISSING = object()
_MAX_VERS_ENTRIES = 32

# Fixed repository-owned messages for the closed error constructor.
_ERROR_REASON_TYPE_MESSAGE = "RoughtimeV19ResponseSemanticError requires a RoughtimeV19ResponseSemanticReason member"
_ERROR_IMMUTABLE_MESSAGE = "RoughtimeV19ResponseSemanticError is immutable after construction"
_ERROR_LOCKED_ATTRS = frozenset({"reason", "_reason", "args"})


class RoughtimeV19ResponseSemanticReason(str, Enum):
    """Closed, exact inventory of deterministic response-semantic reasons.

    Values are repository-standard lowercase identifiers; the member set is closed and never extended at
    runtime. The ``*_structural_invalid`` reasons normalize a K1 structural or K1 bounded-profile rejection at
    that level; they mean "outside the inherited K1 bounded profile or K1-malformed", never a claim about a
    provider's deployed protocol.
    """

    WRONG_INPUT_TYPE = "wrong_input_type"

    OUTER_STRUCTURAL_INVALID = "outer_structural_invalid"
    OUTER_MISSING_MANDATORY_TAG = "outer_missing_mandatory_tag"
    OUTER_SIG_INVALID = "outer_sig_invalid"
    OUTER_NONC_INVALID = "outer_nonc_invalid"
    OUTER_TYPE_INVALID = "outer_type_invalid"
    OUTER_PATH_INVALID = "outer_path_invalid"
    OUTER_INDX_INVALID = "outer_indx_invalid"

    SREP_STRUCTURAL_INVALID = "srep_structural_invalid"
    SREP_MISSING_MANDATORY_TAG = "srep_missing_mandatory_tag"
    SREP_VER_INVALID = "srep_ver_invalid"
    SREP_RADI_INVALID = "srep_radi_invalid"
    SREP_MIDP_INVALID = "srep_midp_invalid"
    SREP_VERS_INVALID = "srep_vers_invalid"
    SREP_ROOT_INVALID = "srep_root_invalid"

    CERT_STRUCTURAL_INVALID = "cert_structural_invalid"
    CERT_MISSING_MANDATORY_TAG = "cert_missing_mandatory_tag"
    CERT_SIG_INVALID = "cert_sig_invalid"

    DELE_STRUCTURAL_INVALID = "dele_structural_invalid"
    DELE_MISSING_MANDATORY_TAG = "dele_missing_mandatory_tag"
    DELE_PUBK_INVALID = "dele_pubk_invalid"
    DELE_MINT_INVALID = "dele_mint_invalid"
    DELE_MAXT_INVALID = "dele_maxt_invalid"
    DELE_INTERVAL_INVALID = "dele_interval_invalid"
    MIDPOINT_OUTSIDE_DELEGATION_INTERVAL = "midpoint_outside_delegation_interval"

    ARTIFACT_DELE_INCONSISTENT = "artifact_dele_inconsistent"
    ARTIFACT_CERT_INCONSISTENT = "artifact_cert_inconsistent"
    ARTIFACT_SREP_INCONSISTENT = "artifact_srep_inconsistent"
    ARTIFACT_RESPONSE_INCONSISTENT = "artifact_response_inconsistent"


class RoughtimeV19ResponseSemanticError(RuntimeError):
    """Raised for every response-semantic failure, carrying exactly one closed reason.

    The constructor accepts ONLY an exact :class:`RoughtimeV19ResponseSemanticReason` member. Any other
    argument raises a plain built-in ``TypeError`` before any attribute of the argument (in particular
    ``.value``) is read, so a hostile ``.value`` property or Enum-like substitute can never run. Once
    constructed the error is immutable: ``reason`` is read-only, its backing storage cannot be substituted,
    ``args`` cannot be replaced, and ``str(error)`` is always exactly ``reason.value``.
    """

    def __init__(self, reason: RoughtimeV19ResponseSemanticReason) -> None:
        if type(reason) is not RoughtimeV19ResponseSemanticReason:
            raise TypeError(_ERROR_REASON_TYPE_MESSAGE)
        object.__setattr__(self, "_reason", reason)
        super().__init__(reason.value)

    @property
    def reason(self) -> RoughtimeV19ResponseSemanticReason:
        return self._reason

    def __setattr__(self, name: str, value: object) -> None:
        if name in _ERROR_LOCKED_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in _ERROR_LOCKED_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        super().__delattr__(name)


def _err(reason: RoughtimeV19ResponseSemanticReason) -> RoughtimeV19ResponseSemanticError:
    return RoughtimeV19ResponseSemanticError(reason)


# --- Primitive semantic decoders (construct no public artifact; never recurse a public constructor) -------
# Each returns exact primitives and raises exactly one closed K2 reason on any violation. Extensions are the
# actual K1 RoughtimeV19Field objects (exact type, canonical wire order) for every non-mandatory tag.


def _require_known_fields(
    message: object,
    mandatory: frozenset[bytes],
    missing_reason: RoughtimeV19ResponseSemanticReason,
) -> tuple[dict[bytes, RoughtimeV19Field], tuple[RoughtimeV19Field, ...]]:
    """Return ``(by_tag, extensions)`` for a K1-parsed message; raise ``missing_reason`` if any mandatory tag
    is absent. K1 guarantees unique canonical tags in ascending wire order, so the extension tuple preserves
    canonical order and excludes every mandatory tag.
    """
    by_tag: dict[bytes, RoughtimeV19Field] = {}
    for field in message.fields:
        by_tag[field.tag] = field
    for tag in mandatory:
        if tag not in by_tag:
            raise _err(missing_reason)
    extensions = tuple(field for field in message.fields if field.tag not in mandatory)
    return by_tag, extensions


def _scalar_uint(
    field: RoughtimeV19Field,
    expected_len: int,
    invalid_reason: RoughtimeV19ResponseSemanticReason,
) -> int:
    """Return the little-endian unsigned integer of an exact-length known field value (K1 guarantees bytes)."""
    if len(field.value) != expected_len:
        raise _err(invalid_reason)
    return int.from_bytes(field.value, "little")


def _decode_path(path_value: bytes) -> tuple[bytes, ...]:
    """Split PATH into exact 32-byte nodes; empty is valid; at most 32 nodes. No hashing, no inclusion check."""
    length = len(path_value)
    if length % _PATH_NODE_BYTES != 0:
        raise _err(RoughtimeV19ResponseSemanticReason.OUTER_PATH_INVALID)
    count = length // _PATH_NODE_BYTES
    if count > _MAX_PATH_NODES:
        raise _err(RoughtimeV19ResponseSemanticReason.OUTER_PATH_INVALID)
    return tuple(path_value[index * _PATH_NODE_BYTES : (index + 1) * _PATH_NODE_BYTES] for index in range(count))


def _decode_versions(vers_value: bytes, selected_version: int) -> tuple[int, ...]:
    """Decode VERS into non-decreasing (ascending) uint32 values; non-empty, 4-aligned, <=32, contains VER.

    Draft-19 requires the RESPONSE VERS list to be sorted in ascending order and to contain the selected
    version, but — unlike the REQUEST VER list — it does NOT prohibit repeated values. Only a strictly
    decreasing relationship is rejected; equal adjacent entries are accepted and preserved verbatim in the
    exposed tuple. (K3, if built, must enforce the request-side no-repetition rule separately.)
    """
    length = len(vers_value)
    if length == 0 or length % _VERS_ENTRY_BYTES != 0:
        raise _err(RoughtimeV19ResponseSemanticReason.SREP_VERS_INVALID)
    count = length // _VERS_ENTRY_BYTES
    if count > _MAX_VERS_ENTRIES:
        raise _err(RoughtimeV19ResponseSemanticReason.SREP_VERS_INVALID)
    values = tuple(
        int.from_bytes(vers_value[index * _VERS_ENTRY_BYTES : (index + 1) * _VERS_ENTRY_BYTES], "little")
        for index in range(count)
    )
    for index in range(1, count):
        if values[index] < values[index - 1]:  # reject only a decreasing relationship; equal is allowed
            raise _err(RoughtimeV19ResponseSemanticReason.SREP_VERS_INVALID)
    if selected_version not in values:
        raise _err(RoughtimeV19ResponseSemanticReason.SREP_VERS_INVALID)
    return values


def _decode_dele_primitive(dele_raw: bytes) -> tuple[bytes, int, int, tuple[RoughtimeV19Field, ...]]:
    """Decode a DELE nested message; return ``(pubk, min_time, max_time, extensions)``.

    Validates the exact PUBK/MINT/MAXT lengths and the local interval ``MINT <= MAXT``. Does not read MIDP
    (the ``MIDP`` interval check is cross-message and lives in the outer decoder).
    """
    try:
        message = parse_roughtime_v19_message(dele_raw)
    except RoughtimeV19KernelError:
        raise _err(RoughtimeV19ResponseSemanticReason.DELE_STRUCTURAL_INVALID) from None
    by_tag, extensions = _require_known_fields(
        message, _DELE_MANDATORY, RoughtimeV19ResponseSemanticReason.DELE_MISSING_MANDATORY_TAG
    )
    pubk = by_tag[_TAG_PUBK].value
    if len(pubk) != _PUBK_BYTES:
        raise _err(RoughtimeV19ResponseSemanticReason.DELE_PUBK_INVALID)
    min_time = _scalar_uint(by_tag[_TAG_MINT], _MINT_BYTES, RoughtimeV19ResponseSemanticReason.DELE_MINT_INVALID)
    max_time = _scalar_uint(by_tag[_TAG_MAXT], _MAXT_BYTES, RoughtimeV19ResponseSemanticReason.DELE_MAXT_INVALID)
    if min_time > max_time:
        raise _err(RoughtimeV19ResponseSemanticReason.DELE_INTERVAL_INVALID)
    return pubk, min_time, max_time, extensions


def _decode_cert_primitive(
    cert_raw: bytes,
) -> tuple[bytes, bytes, tuple[bytes, int, int, tuple[RoughtimeV19Field, ...]], tuple[RoughtimeV19Field, ...]]:
    """Decode a CERT nested message; return ``(signature, dele_raw, dele_primitive, extensions)``.

    Fully decodes the embedded DELE (raising the DELE reason on any DELE violation), so a CERT whose embedded
    DELE is structurally or semantically invalid fails here.
    """
    try:
        message = parse_roughtime_v19_message(cert_raw)
    except RoughtimeV19KernelError:
        raise _err(RoughtimeV19ResponseSemanticReason.CERT_STRUCTURAL_INVALID) from None
    by_tag, extensions = _require_known_fields(
        message, _CERT_MANDATORY, RoughtimeV19ResponseSemanticReason.CERT_MISSING_MANDATORY_TAG
    )
    signature = by_tag[_TAG_SIG].value
    if len(signature) != _SIG_BYTES:
        raise _err(RoughtimeV19ResponseSemanticReason.CERT_SIG_INVALID)
    dele_raw = by_tag[_TAG_DELE].value
    dele_primitive = _decode_dele_primitive(dele_raw)
    return signature, dele_raw, dele_primitive, extensions


def _decode_srep_primitive(
    srep_raw: bytes,
) -> tuple[int, int, int, tuple[int, ...], bytes, tuple[RoughtimeV19Field, ...]]:
    """Decode an SREP nested message; return ``(version, radius, midpoint, versions, root, extensions)``."""
    try:
        message = parse_roughtime_v19_message(srep_raw)
    except RoughtimeV19KernelError:
        raise _err(RoughtimeV19ResponseSemanticReason.SREP_STRUCTURAL_INVALID) from None
    by_tag, extensions = _require_known_fields(
        message, _SREP_MANDATORY, RoughtimeV19ResponseSemanticReason.SREP_MISSING_MANDATORY_TAG
    )
    version = _scalar_uint(by_tag[_TAG_VER], _VER_BYTES, RoughtimeV19ResponseSemanticReason.SREP_VER_INVALID)
    radius = _scalar_uint(by_tag[_TAG_RADI], _RADI_BYTES, RoughtimeV19ResponseSemanticReason.SREP_RADI_INVALID)
    if radius == 0:
        raise _err(RoughtimeV19ResponseSemanticReason.SREP_RADI_INVALID)
    midpoint = _scalar_uint(by_tag[_TAG_MIDP], _MIDP_BYTES, RoughtimeV19ResponseSemanticReason.SREP_MIDP_INVALID)
    versions = _decode_versions(by_tag[_TAG_VERS].value, version)
    root = by_tag[_TAG_ROOT].value
    if len(root) != _ROOT_BYTES:
        raise _err(RoughtimeV19ResponseSemanticReason.SREP_ROOT_INVALID)
    return version, radius, midpoint, versions, root, extensions


def _decode_response_primitive(packet_bytes: bytes) -> tuple[object, ...]:
    """Decode a complete outer response and every nested level; return the primitives needed to build artifacts.

    Order fixes deterministic error precedence: outer structural parse, mandatory outer tags, outer known
    fields, SREP, CERT (which fully decodes DELE), then the cross-message ``MINT <= MIDP <= MAXT`` check.
    """
    try:
        packet = parse_roughtime_v19_packet(packet_bytes)
    except RoughtimeV19KernelError:
        raise _err(RoughtimeV19ResponseSemanticReason.OUTER_STRUCTURAL_INVALID) from None
    by_tag, extensions = _require_known_fields(
        packet.message, _OUTER_MANDATORY, RoughtimeV19ResponseSemanticReason.OUTER_MISSING_MANDATORY_TAG
    )
    signature = by_tag[_TAG_SIG].value
    if len(signature) != _SIG_BYTES:
        raise _err(RoughtimeV19ResponseSemanticReason.OUTER_SIG_INVALID)
    nonce = by_tag[_TAG_NONC].value
    if len(nonce) != _NONC_BYTES:
        raise _err(RoughtimeV19ResponseSemanticReason.OUTER_NONC_INVALID)
    message_type = _scalar_uint(by_tag[_TAG_TYPE], _TYPE_BYTES, RoughtimeV19ResponseSemanticReason.OUTER_TYPE_INVALID)
    if message_type != _TYPE_VALUE:
        raise _err(RoughtimeV19ResponseSemanticReason.OUTER_TYPE_INVALID)
    path = _decode_path(by_tag[_TAG_PATH].value)
    index = _scalar_uint(by_tag[_TAG_INDX], _INDX_BYTES, RoughtimeV19ResponseSemanticReason.OUTER_INDX_INVALID)

    srep_raw = by_tag[_TAG_SREP].value
    srep_primitive = _decode_srep_primitive(srep_raw)
    cert_raw = by_tag[_TAG_CERT].value
    cert_primitive = _decode_cert_primitive(cert_raw)

    midpoint = srep_primitive[2]
    _, _, dele_primitive, _ = cert_primitive
    _, min_time, max_time, _ = dele_primitive
    if not (min_time <= midpoint <= max_time):
        raise _err(RoughtimeV19ResponseSemanticReason.MIDPOINT_OUTSIDE_DELEGATION_INTERVAL)

    return (signature, nonce, message_type, path, index, srep_raw, srep_primitive, cert_raw, cert_primitive, extensions)


# --- Immutable, self-validating public artifacts ----------------------------------------------------------


@dataclass(frozen=True)
class RoughtimeV19DelegationSemantics:
    """DELE delegation semantics, self-validating on direct construction.

    Carries the exact PUBK bytes, the MINT/MAXT little-endian uint64 seconds, preserved unknown ``extensions``
    in canonical wire order, and the exact DELE nested-message ``raw`` bytes. No cryptographic key object is
    built. Direct construction re-decodes ``raw`` and requires every semantic field to equal that primitive
    re-decode; any mismatch, missing/incomplete state, non-exact-type, forged/subclassed component, malformed
    raw, or object built without its initializer raises ``artifact_dele_inconsistent`` (never a leaked
    ``AttributeError``).
    """

    pubk: bytes
    min_time: int
    max_time: int
    extensions: tuple[RoughtimeV19Field, ...]
    raw: bytes

    def __post_init__(self) -> None:
        _validate_delegation_state(self, RoughtimeV19ResponseSemanticReason.ARTIFACT_DELE_INCONSISTENT)


@dataclass(frozen=True)
class RoughtimeV19CertificateSemantics:
    """CERT certificate semantics, self-validating on direct construction.

    Carries the exact 64-byte SIG bytes (never verified), the nested :class:`RoughtimeV19DelegationSemantics`,
    preserved unknown ``extensions`` in canonical wire order, and the exact CERT nested-message ``raw`` bytes.
    Direct construction re-decodes ``raw`` and binds SIG, the extensions, AND the nested delegation's COMPLETE
    current state (pubk, min/max time, extensions, raw) to the exact embedded DELE — matching ``delegation.raw``
    alone is never sufficient. Any mismatch, missing/incomplete state, non-exact-type, or object built without
    its initializer raises ``artifact_cert_inconsistent`` (never a leaked ``AttributeError``).
    """

    signature: bytes
    delegation: RoughtimeV19DelegationSemantics
    extensions: tuple[RoughtimeV19Field, ...]
    raw: bytes

    def __post_init__(self) -> None:
        _validate_certificate_state(self, RoughtimeV19ResponseSemanticReason.ARTIFACT_CERT_INCONSISTENT)


@dataclass(frozen=True)
class RoughtimeV19SignedResponseSemantics:
    """SREP signed-response semantics, self-validating on direct construction.

    Carries the exact selected ``version`` (uint32; exposed only, never asserted operationally admitted), the
    ``radius_seconds`` (uint32, nonzero), the ``midpoint_seconds`` (uint64; never a wall clock), the
    non-decreasing (ascending, duplicates preserved) ``versions`` tuple that contains ``version``, the exact
    32-byte ``root`` (never Merkle-verified), preserved unknown ``extensions`` in canonical wire order, and the
    exact SREP nested-message ``raw`` bytes. Direct construction re-decodes ``raw`` and requires every semantic
    field to equal the primitive re-decode of that exact raw; any mismatch, missing/incomplete state,
    non-exact-type, or forged component raises ``artifact_srep_inconsistent``.
    """

    version: int
    radius_seconds: int
    midpoint_seconds: int
    versions: tuple[int, ...]
    root: bytes
    extensions: tuple[RoughtimeV19Field, ...]
    raw: bytes

    def __post_init__(self) -> None:
        _validate_signed_response_state(self, RoughtimeV19ResponseSemanticReason.ARTIFACT_SREP_INCONSISTENT)


@dataclass(frozen=True)
class RoughtimeV19ResponseSemantics:
    """Complete outer Roughtime response semantics, self-validating on direct construction.

    Carries the exact 64-byte outer ``signature`` (never verified), the 32-byte ``nonce`` (never request-bound),
    the ``message_type`` (uint32 == 1), the ``path`` tuple of exact 32-byte nodes (never Merkle-verified), the
    ``index`` (uint32; never used for inclusion), the nested SREP and CERT artifacts, preserved unknown outer
    ``extensions`` in canonical wire order, and the exact outer packet ``raw`` bytes. Direct construction
    re-decodes ``raw`` (including the cross-message midpoint check) and binds the outer scalars, extensions, AND
    the COMPLETE current state of both nested artifacts to the exact embedded SREP/CERT raw — matching a nested
    ``.raw`` alone is never sufficient. Any mismatch, missing/incomplete state, non-exact-type, or object built
    without its initializer raises ``artifact_response_inconsistent`` (never a leaked ``AttributeError``).
    """

    signature: bytes
    nonce: bytes
    message_type: int
    path: tuple[bytes, ...]
    index: int
    signed_response: RoughtimeV19SignedResponseSemantics
    certificate: RoughtimeV19CertificateSemantics
    extensions: tuple[RoughtimeV19Field, ...]
    raw: bytes

    def __post_init__(self) -> None:
        reason = RoughtimeV19ResponseSemanticReason.ARTIFACT_RESPONSE_INCONSISTENT
        if type(self.raw) is not bytes:
            raise _err(reason)
        try:
            (
                signature,
                nonce,
                message_type,
                path,
                index,
                srep_raw,
                _srep_primitive,
                cert_raw,
                _cert_primitive,
                extensions,
            ) = _decode_response_primitive(self.raw)
        except RoughtimeV19ResponseSemanticError:
            raise _err(reason) from None
        # Outer scalar fields (self's own fields are always set — __post_init__ only runs after __init__).
        if type(self.signature) is not bytes or type(self.nonce) is not bytes or type(self.message_type) is not int:
            raise _err(reason)
        if type(self.path) is not tuple:
            raise _err(reason)
        for node in self.path:
            if type(node) is not bytes:
                raise _err(reason)
        if type(self.index) is not int:
            raise _err(reason)
        if self.signature != signature or self.nonce != nonce or self.message_type != message_type:
            raise _err(reason)
        if self.path != path:
            raise _err(reason)
        if self.index != index:
            raise _err(reason)
        # Nested artifacts: exact type AND complete-state binding to the exact embedded raw. Matching `.raw`
        # alone is never sufficient — every nested semantic field is re-proven against the parent raw's
        # primitive re-decode, safely, so an exact-type object built without its initializer is rejected with
        # this closed reason rather than admitted or leaking a raw exception.
        if type(self.signed_response) is not RoughtimeV19SignedResponseSemantics:  # exact type; subclasses rejected
            raise _err(reason)
        if type(self.certificate) is not RoughtimeV19CertificateSemantics:
            raise _err(reason)
        _validate_signed_response_state(self.signed_response, reason, expected_raw=srep_raw)
        _validate_certificate_state(self.certificate, reason, expected_raw=cert_raw)
        _validate_extensions(self.extensions, extensions, reason)


def _tag_bytes_canonical(tag: bytes) -> bool:
    """Return whether ``tag`` (exactly four bytes) is a canonical draft-19 tag: 1-4 leading uppercase ASCII
    letters then zero padding. K1's private helper is not importable, so this mirrors its rule locally for
    safe validation of caller-supplied extension state; it never mutates or imports K1.
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


def _validate_extensions(
    supplied: object,
    decoded: tuple[RoughtimeV19Field, ...],
    reason: RoughtimeV19ResponseSemanticReason,
) -> None:
    """Validate the COMPLETE state of every supplied extension before any comparison, then bind them to the
    K1-decoded extensions in canonical order.

    Exact class identity (``type(field) is RoughtimeV19Field``) does not prove the field's normal initializer
    ran, so each field's internal state is inspected safely: required attributes present (via ``getattr`` with
    a sentinel — never a caller ``__getattr__`` failure), exact built-in ``bytes`` tag / exact built-in ``int``
    ``tag_uint32`` / exact built-in ``bytes`` value, canonical four-byte tag, and ``tag_uint32`` equal to the
    tag's little-endian integer. Only after those exact-type gates is any value compared, so a hostile
    ``bytes``/``int`` subclass ``__eq__`` can never run first, and an incomplete field raises the closed
    ``reason`` rather than leaking ``AttributeError``. The value comparison (not dataclass ``__eq__``) keeps the
    exact-type gate causally isolated: a value-correct field subclass passes the comparison and is rejected
    only by the type gate.
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


def _validate_delegation_state(
    obj: object,
    reason: RoughtimeV19ResponseSemanticReason,
    *,
    expected_raw: bytes | None = None,
) -> None:
    """Prove an exact-type delegation object's COMPLETE current state matches the primitive re-decode of its own
    exact ``raw`` (and, when ``expected_raw`` is given, that its ``raw`` is exactly the parent-embedded DELE).

    Used both for DELE self-validation and by a parent certificate to admit a nested delegation. Reading state
    with ``getattr`` + sentinel and exact-type gates before any value comparison means an object built without
    its initializer, a subsequently mutated object, or a wrong internal type raises ``reason`` and never leaks
    ``AttributeError``/``TypeError``/etc.
    """
    raw = getattr(obj, "raw", _MISSING)
    if raw is _MISSING or type(raw) is not bytes:
        raise _err(reason)
    if expected_raw is not None and raw != expected_raw:
        raise _err(reason)
    try:
        pubk, min_time, max_time, extensions = _decode_dele_primitive(raw)
    except RoughtimeV19ResponseSemanticError:
        raise _err(reason) from None
    obj_pubk = getattr(obj, "pubk", _MISSING)
    obj_min = getattr(obj, "min_time", _MISSING)
    obj_max = getattr(obj, "max_time", _MISSING)
    obj_ext = getattr(obj, "extensions", _MISSING)
    if obj_pubk is _MISSING or obj_min is _MISSING or obj_max is _MISSING or obj_ext is _MISSING:
        raise _err(reason)
    if type(obj_pubk) is not bytes or type(obj_min) is not int or type(obj_max) is not int:
        raise _err(reason)
    if obj_pubk != pubk or obj_min != min_time or obj_max != max_time:
        raise _err(reason)
    _validate_extensions(obj_ext, extensions, reason)


def _validate_signed_response_state(
    obj: object,
    reason: RoughtimeV19ResponseSemanticReason,
    *,
    expected_raw: bytes | None = None,
) -> None:
    """Prove an exact-type signed-response object's COMPLETE current state matches the primitive re-decode of its
    own exact SREP ``raw`` (and its ``raw`` equals ``expected_raw`` when a parent supplies it). Safe against
    objects built without their initializer or mutated after construction; never leaks a raw exception.
    """
    raw = getattr(obj, "raw", _MISSING)
    if raw is _MISSING or type(raw) is not bytes:
        raise _err(reason)
    if expected_raw is not None and raw != expected_raw:
        raise _err(reason)
    try:
        version, radius, midpoint, versions, root, extensions = _decode_srep_primitive(raw)
    except RoughtimeV19ResponseSemanticError:
        raise _err(reason) from None
    obj_version = getattr(obj, "version", _MISSING)
    obj_radius = getattr(obj, "radius_seconds", _MISSING)
    obj_midpoint = getattr(obj, "midpoint_seconds", _MISSING)
    obj_versions = getattr(obj, "versions", _MISSING)
    obj_root = getattr(obj, "root", _MISSING)
    obj_ext = getattr(obj, "extensions", _MISSING)
    if (
        obj_version is _MISSING
        or obj_radius is _MISSING
        or obj_midpoint is _MISSING
        or obj_versions is _MISSING
        or obj_root is _MISSING
        or obj_ext is _MISSING
    ):
        raise _err(reason)
    if type(obj_version) is not int or type(obj_radius) is not int or type(obj_midpoint) is not int:
        raise _err(reason)
    if type(obj_root) is not bytes or type(obj_versions) is not tuple:
        raise _err(reason)
    for entry in obj_versions:
        if type(entry) is not int:  # exact int per version entry; bool and int subclasses rejected
            raise _err(reason)
    if obj_version != version or obj_radius != radius or obj_midpoint != midpoint:
        raise _err(reason)
    if obj_versions != versions or obj_root != root:
        raise _err(reason)
    _validate_extensions(obj_ext, extensions, reason)


def _validate_certificate_state(
    obj: object,
    reason: RoughtimeV19ResponseSemanticReason,
    *,
    expected_raw: bytes | None = None,
) -> None:
    """Prove an exact-type certificate object's COMPLETE current state matches the primitive re-decode of its own
    exact CERT ``raw`` — signature, extensions, and the nested delegation's complete state bound to the exact
    embedded DELE raw (never trusting ``delegation.raw`` alone). Safe against uninitialized or mutated objects;
    never leaks a raw exception.
    """
    raw = getattr(obj, "raw", _MISSING)
    if raw is _MISSING or type(raw) is not bytes:
        raise _err(reason)
    if expected_raw is not None and raw != expected_raw:
        raise _err(reason)
    try:
        signature, dele_raw, _dele_primitive, extensions = _decode_cert_primitive(raw)
    except RoughtimeV19ResponseSemanticError:
        raise _err(reason) from None
    obj_signature = getattr(obj, "signature", _MISSING)
    obj_delegation = getattr(obj, "delegation", _MISSING)
    obj_ext = getattr(obj, "extensions", _MISSING)
    if obj_signature is _MISSING or obj_delegation is _MISSING or obj_ext is _MISSING:
        raise _err(reason)
    if type(obj_signature) is not bytes:
        raise _err(reason)
    if obj_signature != signature:
        raise _err(reason)
    if type(obj_delegation) is not RoughtimeV19DelegationSemantics:  # exact type; subclasses rejected
        raise _err(reason)
    _validate_extensions(obj_ext, extensions, reason)
    _validate_delegation_state(obj_delegation, reason, expected_raw=dele_raw)


# --- Builders (assemble artifacts from already-decoded primitives) ----------------------------------------


def _build_delegation(
    dele_raw: bytes,
    dele_primitive: tuple[bytes, int, int, tuple[RoughtimeV19Field, ...]],
) -> RoughtimeV19DelegationSemantics:
    pubk, min_time, max_time, extensions = dele_primitive
    return RoughtimeV19DelegationSemantics(
        pubk=pubk, min_time=min_time, max_time=max_time, extensions=extensions, raw=dele_raw
    )


def _build_certificate(
    cert_raw: bytes,
    cert_primitive: tuple[
        bytes, bytes, tuple[bytes, int, int, tuple[RoughtimeV19Field, ...]], tuple[RoughtimeV19Field, ...]
    ],
) -> RoughtimeV19CertificateSemantics:
    signature, dele_raw, dele_primitive, extensions = cert_primitive
    delegation = _build_delegation(dele_raw, dele_primitive)
    return RoughtimeV19CertificateSemantics(
        signature=signature, delegation=delegation, extensions=extensions, raw=cert_raw
    )


def _build_signed_response(
    srep_raw: bytes,
    srep_primitive: tuple[int, int, int, tuple[int, ...], bytes, tuple[RoughtimeV19Field, ...]],
) -> RoughtimeV19SignedResponseSemantics:
    version, radius, midpoint, versions, root, extensions = srep_primitive
    return RoughtimeV19SignedResponseSemantics(
        version=version,
        radius_seconds=radius,
        midpoint_seconds=midpoint,
        versions=versions,
        root=root,
        extensions=extensions,
        raw=srep_raw,
    )


def parse_roughtime_v19_response(packet_bytes: bytes) -> RoughtimeV19ResponseSemantics:
    """Parse and semantically validate a Roughtime draft-19 response within the inherited K1 bounded profile.

    Accepts exact built-in ``bytes`` only. Delegates all structural work to the K1 public parser, validates
    the mandatory outer/SREP/CERT/DELE tags and their non-cryptographic value constraints, preserves every
    unknown tag as an extension, binds the exact raw bytes for future signature verification, and returns an
    immutable :class:`RoughtimeV19ResponseSemantics`. Performs no cryptography, no provider binding, no
    network/clock access, and causes no readiness or connector transition.
    """
    if type(packet_bytes) is not bytes:
        raise _err(RoughtimeV19ResponseSemanticReason.WRONG_INPUT_TYPE)
    (
        signature,
        nonce,
        message_type,
        path,
        index,
        srep_raw,
        srep_primitive,
        cert_raw,
        cert_primitive,
        extensions,
    ) = _decode_response_primitive(packet_bytes)
    signed_response = _build_signed_response(srep_raw, srep_primitive)
    certificate = _build_certificate(cert_raw, cert_primitive)
    return RoughtimeV19ResponseSemantics(
        signature=signature,
        nonce=nonce,
        message_type=message_type,
        path=path,
        index=index,
        signed_response=signed_response,
        certificate=certificate,
        extensions=extensions,
        raw=packet_bytes,
    )


__all__ = [
    "ROUGHTIME_V19_RESPONSE_SEMANTIC_PROFILE_ID",
    "RoughtimeV19CertificateSemantics",
    "RoughtimeV19DelegationSemantics",
    "RoughtimeV19ResponseSemantics",
    "RoughtimeV19ResponseSemanticError",
    "RoughtimeV19ResponseSemanticReason",
    "RoughtimeV19SignedResponseSemantics",
    "parse_roughtime_v19_response",
]
