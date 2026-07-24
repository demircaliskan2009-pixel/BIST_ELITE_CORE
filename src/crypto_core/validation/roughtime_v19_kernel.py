"""Roughtime draft-19 bounded structural kernel (internal MT-4 prerequisite K1) — provider-independent.

This module is a pure STRUCTURAL parser for the Roughtime draft-19 wire framing: the outer packet envelope
and the generic tag/value message layout. It exists as the first internal MT-4 prerequisite so that later
machine-time work can reason about Roughtime bytes without re-deriving the framing rules. It is deterministic
and fully self-contained.

Bounded profile (honest scope): this kernel implements ONE governance-selected, versioned, bounded
structural profile, identified by :data:`ROUGHTIME_V19_STRUCTURAL_PROFILE_ID`
(``"roughtime-v19-structural-bounded-k1.v1"``). The profile pins controller-owned maximum packet-byte,
message-byte and pair-count limits (:data:`ROUGHTIME_V19_MAX_PACKET_BYTES`,
:data:`ROUGHTIME_V19_MAX_MESSAGE_BYTES`, :data:`ROUGHTIME_V19_MAX_PAIR_COUNT`). These limits are:

* implementation bounds, NOT draft-19 protocol limits (draft-19 defines no matching maximum);
* NOT evidence that a larger input is malformed;
* NOT proof of complete draft-19 structural coverage.

Therefore NOT all structurally valid draft-19 messages are necessarily accepted. An input that exceeds a
profile limit is reported as OUTSIDE THIS BOUNDED PROFILE (reasons ``profile_packet_bytes_exceeded`` /
``profile_message_bytes_exceeded`` / ``profile_pair_count_exceeded``), never as generally invalid or
malformed Roughtime. No consumer may convert a profile-limit rejection into a protocol-invalid claim, and no
consumer may infer that an over-limit input is malformed. Exact raw replay of arbitrary provenance bytes
beyond this profile is UNSUPPORTED; a broader parser or replay profile requires separate governance.

Defensible rationale for the bounded profile: it keeps memory and CPU deterministically bounded, uses no
recursion, runs in O(N), and caps header allocation at ``8 * 64 = 512`` bytes under the profile. The profile
is intentionally narrow and separately versioned.

Scope — what this kernel does within the bounded profile:

* validates the outer packet frame (8-byte ``ROUGHTIM`` magic + little-endian ``uint32`` declared message
  length + exactly one message, with no trailing and no missing bytes);
* validates the generic message layout (``uint32`` pair count ``N``; ``N-1`` little-endian ``uint32``
  offsets; ``N`` little-endian ``uint32`` tags; an opaque values section);
* validates offsets (four-byte aligned, non-decreasing, never past the values section; equal adjacent
  offsets are allowed because zero-length values are permitted);
* validates tags (four raw bytes, one to four leading uppercase ASCII letters followed only by zero
  padding, ordered strictly ascending by little-endian ``uint32`` value, never duplicated);
* preserves every value as exact opaque bytes and preserves the exact original packet and message bytes.

Self-validating artifacts and closed error contract: the public parsed-artifact classes
(:class:`RoughtimeV19Field`, :class:`RoughtimeV19Message`, :class:`RoughtimeV19Packet`) self-validate direct
construction against a primitive re-decode of their own raw bytes, so a directly constructed artifact can
never represent parsed fields that differ from its exact raw bytes. :class:`RoughtimeV19KernelError` accepts
only an exact :class:`RoughtimeV19KernelReason` member (a wrong constructor input raises a plain built-in
``TypeError`` before any attribute of the argument is read), and is immutable after construction.

Scope boundary — what this kernel is NOT:

* structural parser only — it performs no cryptographic verification (no signatures, no Merkle-proof
  checking);
* it binds no provider, endpoint, or public key and carries no provider metadata;
* it proves no time and reads no wall clock;
* it performs no network access, no filesystem access, no environment access, and uses no randomness;
* it builds no request and validates no request or response semantics;
* values are opaque — nested Roughtime messages are NOT recursively interpreted in K1;
* it reads or mutates no other machine-time artifact (in particular no source registry and no anchor
  evidence);
* it has no readiness or connector effect and triggers no readiness or connector transition.

The only claim this kernel supports is that it accepts and rejects deterministic synthetic byte sequences
according to the reviewed draft-19 framing and generic-message rules, within this bounded profile; it makes
no stronger claim.

Trust boundary: both public parsers accept exact built-in ``bytes`` only and reject ``bytearray``,
``memoryview``, ``bytes`` subclasses, and every non-bytes value before any other operation. No caller value
participates in any indexing, slicing, arithmetic, or comparison until its exact type is proven, and every
domain failure raises :class:`RoughtimeV19KernelError` carrying exactly one closed member of
:class:`RoughtimeV19KernelReason`; no raw ``ValueError``/``IndexError``/``TypeError``/``OverflowError`` is
ever leaked, and no ``BaseException``/``KeyboardInterrupt``/``SystemExit``/``GeneratorExit`` is caught.

Versioned specification: https://datatracker.ietf.org/doc/html/draft-ietf-ntp-roughtime-19
Immutable official source snapshot reviewed: ietf-wg-ntp/draft-roughtime @
6157257b8ff618293e2ae379cf78e060fe975411 (described only as the immutable official source snapshot
reviewed; not asserted to be the exact publication-generation commit).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# --- Outer-frame and word constants (protocol structure) -------------------------------------------------
_ROUGHTIME_MAGIC = b"ROUGHTIM"
_MAGIC_LENGTH = len(_ROUGHTIME_MAGIC)  # 8
_UINT32_BYTES = 4
_LENGTH_FIELD_BYTES = _UINT32_BYTES  # little-endian uint32 declared message length
_PACKET_FRAME_BYTES = _MAGIC_LENGTH + _LENGTH_FIELD_BYTES  # 12: magic + declared length
_OFFSET_ALIGNMENT = 4  # draft-19 offsets are multiples of four bytes

# Uppercase ASCII letter range used for tag canonicality (raw byte values).
_UPPER_A = 0x41  # "A"
_UPPER_Z = 0x5A  # "Z"

# --- Bounded structural profile (governance-selected, versioned) -----------------------------------------
# These are controller-owned implementation bounds for ONE narrow, separately versioned structural profile.
# They are NOT draft-19 protocol limits and are NOT evidence that a larger input is malformed: draft-19
# defines no matching maximum, and an over-limit input is reported as OUTSIDE THIS PROFILE, never as invalid
# Roughtime. The bounds exist only to keep memory and CPU deterministically bounded (no recursion, O(N),
# header allocation capped at 8 * 64 = 512 bytes under the profile). A broader parser/replay profile, and
# exact raw replay of arbitrary provenance bytes beyond this profile, require separate governance.
ROUGHTIME_V19_STRUCTURAL_PROFILE_ID = "roughtime-v19-structural-bounded-k1.v1"
ROUGHTIME_V19_MAX_PACKET_BYTES = 4096
ROUGHTIME_V19_MAX_MESSAGE_BYTES = ROUGHTIME_V19_MAX_PACKET_BYTES - _PACKET_FRAME_BYTES  # 4084
ROUGHTIME_V19_MAX_PAIR_COUNT = 64

# Structural minimums that make a frame/message decodable (not profile ceilings).
_MIN_MESSAGE_BYTES = _UINT32_BYTES  # the mandatory 4-byte pair-count word
_MIN_PACKET_BYTES = _PACKET_FRAME_BYTES  # magic + declared length

# Fixed repository-owned messages for the closed error constructor.
_ERROR_REASON_TYPE_MESSAGE = "RoughtimeV19KernelError requires a RoughtimeV19KernelReason member"
_ERROR_IMMUTABLE_MESSAGE = "RoughtimeV19KernelError is immutable after construction"
_ERROR_LOCKED_ATTRS = frozenset({"reason", "_reason", "args"})


class RoughtimeV19KernelReason(str, Enum):
    """Closed, exact inventory of deterministic structural-parse and artifact-validation reasons.

    Values are repository-standard lowercase identifiers; the member set is closed and never extended at
    runtime. The three ``profile_*`` reasons denote an input that is OUTSIDE THIS BOUNDED PROFILE, not an
    input proven to be malformed draft-19.
    """

    WRONG_INPUT_TYPE = "wrong_input_type"
    PACKET_TOO_SHORT = "packet_too_short"
    PROFILE_PACKET_BYTES_EXCEEDED = "profile_packet_bytes_exceeded"
    PACKET_MAGIC_MISMATCH = "packet_magic_mismatch"
    PACKET_MESSAGE_LENGTH_MISMATCH = "packet_message_length_mismatch"
    MESSAGE_TOO_SHORT = "message_too_short"
    PROFILE_MESSAGE_BYTES_EXCEEDED = "profile_message_bytes_exceeded"
    PAIR_COUNT_ZERO = "pair_count_zero"
    PROFILE_PAIR_COUNT_EXCEEDED = "profile_pair_count_exceeded"
    HEADER_TRUNCATED = "header_truncated"
    OFFSET_UNALIGNED = "offset_unaligned"
    OFFSET_ORDER_INVALID = "offset_order_invalid"
    OFFSET_OUT_OF_BOUNDS = "offset_out_of_bounds"
    TAG_INVALID = "tag_invalid"
    TAG_ORDER_INVALID = "tag_order_invalid"
    TAG_DUPLICATE = "tag_duplicate"
    ARTIFACT_FIELD_INCONSISTENT = "artifact_field_inconsistent"
    ARTIFACT_MESSAGE_INCONSISTENT = "artifact_message_inconsistent"
    ARTIFACT_PACKET_INCONSISTENT = "artifact_packet_inconsistent"


class RoughtimeV19KernelError(RuntimeError):
    """Raised for every Roughtime structural-parse or artifact-validation failure, carrying one closed reason.

    The constructor accepts ONLY an exact :class:`RoughtimeV19KernelReason` member. Any other argument raises
    a plain built-in ``TypeError`` before any attribute of the argument (in particular ``.value``) is read,
    so a hostile ``.value`` property or Enum-like substitute can never run. Once constructed the error is
    immutable: ``reason`` is read-only, its backing storage cannot be substituted, ``args`` cannot be
    replaced, and ``str(error)`` is always exactly ``reason.value``.
    """

    def __init__(self, reason: RoughtimeV19KernelReason) -> None:
        if type(reason) is not RoughtimeV19KernelReason:
            raise TypeError(_ERROR_REASON_TYPE_MESSAGE)
        object.__setattr__(self, "_reason", reason)
        super().__init__(reason.value)

    @property
    def reason(self) -> RoughtimeV19KernelReason:
        return self._reason

    def __setattr__(self, name: str, value: object) -> None:
        if name in _ERROR_LOCKED_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in _ERROR_LOCKED_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        super().__delattr__(name)


def _tag_is_canonical(tag: bytes) -> bool:
    """Return whether ``tag`` (exactly four bytes) is a canonical draft-19 tag.

    A canonical tag is one to four leading uppercase ASCII letters followed only by zero padding, and is
    never all zero.
    """
    if not (_UPPER_A <= tag[0] <= _UPPER_Z):
        return False
    letters = 1
    while letters < _UINT32_BYTES and _UPPER_A <= tag[letters] <= _UPPER_Z:
        letters += 1
    padding_index = letters
    while padding_index < _UINT32_BYTES:
        if tag[padding_index] != 0:
            return False
        padding_index += 1
    return True


def _decode_message_primitive(
    message_bytes: bytes,
) -> tuple[int, tuple[tuple[bytes, int, bytes], ...]]:
    """Validate ``message_bytes`` under the bounded profile and return primitive components.

    Returns ``(pair_count, fields_primitive)`` where each ``fields_primitive`` element is a
    ``(tag_bytes, tag_uint32, value_bytes)`` triple. Constructs no public artifact and never recurses through
    a public constructor. Raises :class:`RoughtimeV19KernelError` on any structural or profile violation.
    """
    if type(message_bytes) is not bytes:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.WRONG_INPUT_TYPE)

    length = len(message_bytes)
    if length > ROUGHTIME_V19_MAX_MESSAGE_BYTES:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PROFILE_MESSAGE_BYTES_EXCEEDED)
    if length < _MIN_MESSAGE_BYTES:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.MESSAGE_TOO_SHORT)

    pair_count = int.from_bytes(message_bytes[0:_UINT32_BYTES], "little")
    if pair_count < 1:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PAIR_COUNT_ZERO)
    if pair_count > ROUGHTIME_V19_MAX_PAIR_COUNT:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PROFILE_PAIR_COUNT_EXCEEDED)

    # Header layout: one uint32 pair-count word, then N-1 offset words, then N tag words (== 8 * N bytes).
    count_field_bytes = _UINT32_BYTES
    offsets_bytes = (pair_count - 1) * _UINT32_BYTES
    tags_bytes = pair_count * _UINT32_BYTES
    header_length = count_field_bytes + offsets_bytes + tags_bytes
    if length < header_length:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.HEADER_TRUNCATED)

    values = message_bytes[header_length:]
    values_length = len(values)

    # Decode and validate the N-1 explicit offsets. The first value's offset is implicitly zero. Only the
    # explicit offsets must be four-byte aligned; the final value (after the last explicit offset) may be any
    # length.
    offsets_start = count_field_bytes
    boundaries = [0]
    previous = 0
    for index in range(pair_count - 1):
        start = offsets_start + _UINT32_BYTES * index
        offset = int.from_bytes(message_bytes[start : start + _UINT32_BYTES], "little")
        if offset % _OFFSET_ALIGNMENT != 0:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.OFFSET_UNALIGNED)
        if offset < previous:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.OFFSET_ORDER_INVALID)
        if offset > values_length:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.OFFSET_OUT_OF_BOUNDS)
        boundaries.append(offset)
        previous = offset
    boundaries.append(values_length)

    # Decode and validate the N tags (canonical form first, then strict little-endian ordering). Strict
    # wire-order validation reaches the first descending relationship before a non-adjacent duplicate could
    # be treated as an adjacent duplicate: a non-adjacent duplicate therefore surfaces as TAG_ORDER_INVALID.
    tags_start = offsets_start + offsets_bytes
    tags = []
    tag_values = []
    for index in range(pair_count):
        start = tags_start + _UINT32_BYTES * index
        tag = message_bytes[start : start + _UINT32_BYTES]
        if not _tag_is_canonical(tag):
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.TAG_INVALID)
        tags.append(tag)
        tag_values.append(int.from_bytes(tag, "little"))

    for index in range(1, pair_count):
        if tag_values[index] == tag_values[index - 1]:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.TAG_DUPLICATE)
        if tag_values[index] < tag_values[index - 1]:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.TAG_ORDER_INVALID)

    fields_primitive = tuple(
        (tags[index], tag_values[index], values[boundaries[index] : boundaries[index + 1]])
        for index in range(pair_count)
    )
    return pair_count, fields_primitive


def _decode_packet_frame_primitive(packet_bytes: bytes) -> tuple[bytes, int, bytes]:
    """Validate the outer frame under the bounded profile; return ``(magic, declared_length, message_bytes)``.

    Does not parse the enclosed message and constructs no public artifact. Raises
    :class:`RoughtimeV19KernelError` on any structural or profile violation.
    """
    if type(packet_bytes) is not bytes:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.WRONG_INPUT_TYPE)

    length = len(packet_bytes)
    if length > ROUGHTIME_V19_MAX_PACKET_BYTES:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PROFILE_PACKET_BYTES_EXCEEDED)
    if length < _MIN_PACKET_BYTES:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PACKET_TOO_SHORT)

    if packet_bytes[0:_MAGIC_LENGTH] != _ROUGHTIME_MAGIC:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PACKET_MAGIC_MISMATCH)

    declared_length = int.from_bytes(packet_bytes[_MAGIC_LENGTH : _MAGIC_LENGTH + _LENGTH_FIELD_BYTES], "little")
    message_bytes = packet_bytes[_PACKET_FRAME_BYTES:]
    if declared_length != len(message_bytes):
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PACKET_MESSAGE_LENGTH_MISMATCH)
    return _ROUGHTIME_MAGIC, declared_length, message_bytes


@dataclass(frozen=True)
class RoughtimeV19Field:
    """One parsed tag/value pair, self-validating on direct construction.

    ``tag`` is the exact four raw tag bytes, ``tag_uint32`` is their little-endian numeric interpretation
    (the value that defines tag ordering), and ``value`` is the exact opaque value bytes. Nested Roughtime
    messages inside ``value`` are never recursively interpreted in K1. Direct construction with an
    inconsistent, non-exact-type, or non-canonical component raises
    :class:`RoughtimeV19KernelError` (``artifact_field_inconsistent``).
    """

    tag: bytes
    tag_uint32: int
    value: bytes

    def __post_init__(self) -> None:
        if type(self.tag) is not bytes:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_FIELD_INCONSISTENT)
        if len(self.tag) != _UINT32_BYTES:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_FIELD_INCONSISTENT)
        if not _tag_is_canonical(self.tag):
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_FIELD_INCONSISTENT)
        if type(self.tag_uint32) is not int:  # exact int; bool (a subclass) is rejected
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_FIELD_INCONSISTENT)
        if self.tag_uint32 != int.from_bytes(self.tag, "little"):
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_FIELD_INCONSISTENT)
        if type(self.value) is not bytes:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_FIELD_INCONSISTENT)


@dataclass(frozen=True)
class RoughtimeV19Message:
    """A parsed generic Roughtime message, self-validating on direct construction.

    ``fields`` are the ``pair_count`` tag/value pairs in canonical wire order and ``raw`` is the exact
    original message bytes. Direct construction re-decodes ``raw`` under the bounded profile and requires the
    reparsed pair count, field count and every ``(tag, tag_uint32, value)`` to match the supplied fields
    exactly; any mismatch, non-exact-type, or forged/subclassed field raises
    :class:`RoughtimeV19KernelError` (``artifact_message_inconsistent``). A directly constructed message can
    therefore never represent parsed fields that differ from its exact raw bytes.
    """

    pair_count: int
    fields: tuple[RoughtimeV19Field, ...]
    raw: bytes

    def __post_init__(self) -> None:
        if type(self.pair_count) is not int:  # exact int; bool is rejected
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_MESSAGE_INCONSISTENT)
        if type(self.fields) is not tuple:  # exact tuple; list and tuple subclasses are rejected
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_MESSAGE_INCONSISTENT)
        for field in self.fields:
            if type(field) is not RoughtimeV19Field:  # exact type; forgeries and subclasses rejected
                raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_MESSAGE_INCONSISTENT)
        if type(self.raw) is not bytes:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_MESSAGE_INCONSISTENT)
        try:
            reparsed_count, reparsed_fields = _decode_message_primitive(self.raw)
        except RoughtimeV19KernelError:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_MESSAGE_INCONSISTENT) from None
        if reparsed_count != self.pair_count:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_MESSAGE_INCONSISTENT)
        if len(reparsed_fields) != len(self.fields):
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_MESSAGE_INCONSISTENT)
        for index in range(len(self.fields)):
            supplied = self.fields[index]
            tag, tag_uint32, value = reparsed_fields[index]
            if supplied.tag != tag or supplied.tag_uint32 != tag_uint32 or supplied.value != value:
                raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_MESSAGE_INCONSISTENT)


@dataclass(frozen=True)
class RoughtimeV19Packet:
    """A parsed Roughtime outer packet, self-validating on direct construction.

    Direct construction re-decodes the outer frame of ``raw`` under the bounded profile and requires the
    magic, the declared length, and the embedded message bytes (which must equal ``message.raw``) to match
    the supplied components exactly, and requires a primitive re-decode of the embedded message bytes to
    match the supplied message artifact exactly; any mismatch, non-exact-type, or forged/subclassed message
    raises :class:`RoughtimeV19KernelError` (``artifact_packet_inconsistent``).
    """

    magic: bytes
    message_length: int
    message: RoughtimeV19Message
    raw: bytes

    def __post_init__(self) -> None:
        if type(self.magic) is not bytes:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT)
        if self.magic != _ROUGHTIME_MAGIC:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT)
        if type(self.message_length) is not int:  # exact int; bool is rejected
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT)
        if type(self.message) is not RoughtimeV19Message:  # exact type; forgeries and subclasses rejected
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT)
        if type(self.raw) is not bytes:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT)
        try:
            _, declared_length, message_bytes = _decode_packet_frame_primitive(self.raw)
        except RoughtimeV19KernelError:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT) from None
        if declared_length != self.message_length:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT)
        if message_bytes != self.message.raw:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT)
        try:
            reparsed_count, reparsed_fields = _decode_message_primitive(message_bytes)
        except RoughtimeV19KernelError:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT) from None
        if reparsed_count != self.message.pair_count:
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT)
        if len(reparsed_fields) != len(self.message.fields):
            raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT)
        for index in range(len(self.message.fields)):
            supplied = self.message.fields[index]
            tag, tag_uint32, value = reparsed_fields[index]
            if supplied.tag != tag or supplied.tag_uint32 != tag_uint32 or supplied.value != value:
                raise RoughtimeV19KernelError(RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT)


def parse_roughtime_v19_message(message_bytes: bytes) -> RoughtimeV19Message:
    """Parse and structurally validate a generic Roughtime message within the bounded profile.

    Accepts exact built-in ``bytes`` only. Over-limit inputs are rejected as OUTSIDE THIS PROFILE, never as
    malformed Roughtime. Values are preserved as exact opaque bytes; no tag is semantically interpreted.
    """
    pair_count, fields_primitive = _decode_message_primitive(message_bytes)
    fields = tuple(
        RoughtimeV19Field(tag=tag, tag_uint32=tag_uint32, value=value) for tag, tag_uint32, value in fields_primitive
    )
    return RoughtimeV19Message(pair_count=pair_count, fields=fields, raw=message_bytes)


def parse_roughtime_v19_packet(packet_bytes: bytes) -> RoughtimeV19Packet:
    """Parse and structurally validate a Roughtime outer packet within the bounded profile.

    Accepts exact built-in ``bytes`` only. Validates the magic and declared message length, then parses the
    exact enclosed message bytes with :func:`parse_roughtime_v19_message`. Over-limit inputs are rejected as
    OUTSIDE THIS PROFILE, never as malformed Roughtime.
    """
    magic, declared_length, message_bytes = _decode_packet_frame_primitive(packet_bytes)
    message = parse_roughtime_v19_message(message_bytes)
    return RoughtimeV19Packet(
        magic=magic,
        message_length=declared_length,
        message=message,
        raw=packet_bytes,
    )


__all__ = [
    "ROUGHTIME_V19_MAX_MESSAGE_BYTES",
    "ROUGHTIME_V19_MAX_PACKET_BYTES",
    "ROUGHTIME_V19_MAX_PAIR_COUNT",
    "ROUGHTIME_V19_STRUCTURAL_PROFILE_ID",
    "RoughtimeV19Field",
    "RoughtimeV19KernelError",
    "RoughtimeV19KernelReason",
    "RoughtimeV19Message",
    "RoughtimeV19Packet",
    "parse_roughtime_v19_message",
    "parse_roughtime_v19_packet",
]
