"""Roughtime draft-19 structural kernel (internal MT-4 prerequisite K1) — provider-independent, deterministic.

This module is a pure STRUCTURAL parser for the Roughtime draft-19 wire framing: the outer packet envelope
and the generic tag/value message layout. It exists as the first internal MT-4 prerequisite so that later
machine-time anchor work can reason about Roughtime bytes without re-deriving the framing rules. It is
deterministic and fully self-contained.

Scope — what this kernel does:

* validates the outer packet frame (8-byte ``ROUGHTIM`` magic + little-endian ``uint32`` declared message
  length + exactly one message, with no trailing and no missing bytes);
* validates the generic message layout (``uint32`` pair count ``N``; ``N-1`` little-endian ``uint32``
  offsets; ``N`` little-endian ``uint32`` tags; an opaque values section);
* validates offsets (four-byte aligned, non-decreasing, never past the values section; equal adjacent
  offsets are allowed because zero-length values are permitted);
* validates tags (four raw bytes, one to four leading uppercase ASCII letters followed only by zero
  padding, ordered strictly ascending by little-endian ``uint32`` value, never duplicated);
* preserves every value as exact opaque bytes and preserves the exact original packet and message bytes.

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
according to the reviewed draft-19 framing and generic-message rules; it makes no stronger claim.

Trust boundary: both public parsers accept exact built-in ``bytes`` only and reject ``bytearray``,
``memoryview``, ``bytes`` subclasses, and every non-bytes value before any other operation. No caller value
participates in any indexing, slicing, arithmetic, or comparison until its exact type is proven, and every
domain failure raises :class:`RoughtimeV19KernelError` carrying exactly one closed member of
:class:`RoughtimeV19KernelReason`; no raw ``ValueError``/``IndexError``/``TypeError``/``OverflowError`` is
ever leaked.

The size and pair-count limits below are controller-owned implementation-defense ceilings, not protocol
facts.

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

# --- Controller-owned defensive ceilings (implementation defense, NOT protocol constants) ----------------
# draft-19 exchanges are designed to fit in a single unfragmented UDP datagram: requests are padded to at
# least 1024 bytes and responses are well under 1 KB, so a standard 1500-byte Ethernet MTU is a comfortable
# structural ceiling that still bounds memory. The message ceiling is the packet ceiling minus the 12-byte
# outer frame. Realistic messages carry only a handful of top-level tags, so 64 is a generous pair-count
# ceiling that bounds header allocation to 8 * 64 = 512 bytes. No caller may override these.
_MAX_PACKET_BYTES = 1500
_MAX_MESSAGE_BYTES = _MAX_PACKET_BYTES - _PACKET_FRAME_BYTES  # 1488
_MAX_PAIR_COUNT = 64

# Minimums that make a frame/message structurally decodable.
_MIN_MESSAGE_BYTES = _UINT32_BYTES  # the mandatory 4-byte pair-count word
_MIN_PACKET_BYTES = _PACKET_FRAME_BYTES  # magic + declared length


class RoughtimeV19KernelReason(str, Enum):
    """Closed, exact inventory of deterministic structural-parse failure reasons.

    Values are repository-standard lowercase identifiers; the member set is closed and never extended at
    runtime.
    """

    WRONG_INPUT_TYPE = "wrong_input_type"
    PACKET_TOO_SHORT = "packet_too_short"
    PACKET_TOO_LARGE = "packet_too_large"
    PACKET_MAGIC_MISMATCH = "packet_magic_mismatch"
    PACKET_MESSAGE_LENGTH_MISMATCH = "packet_message_length_mismatch"
    MESSAGE_TOO_SHORT = "message_too_short"
    MESSAGE_TOO_LARGE = "message_too_large"
    PAIR_COUNT_ZERO = "pair_count_zero"
    PAIR_COUNT_EXCEEDS_LIMIT = "pair_count_exceeds_limit"
    HEADER_TRUNCATED = "header_truncated"
    OFFSET_UNALIGNED = "offset_unaligned"
    OFFSET_ORDER_INVALID = "offset_order_invalid"
    OFFSET_OUT_OF_BOUNDS = "offset_out_of_bounds"
    TAG_INVALID = "tag_invalid"
    TAG_ORDER_INVALID = "tag_order_invalid"
    TAG_DUPLICATE = "tag_duplicate"


class RoughtimeV19KernelError(RuntimeError):
    """Raised for every Roughtime draft-19 structural-parse failure, carrying exactly one closed reason."""

    def __init__(self, reason: RoughtimeV19KernelReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


@dataclass(frozen=True)
class RoughtimeV19Field:
    """One parsed tag/value pair.

    ``tag`` is the exact four raw tag bytes, ``tag_uint32`` is their little-endian numeric interpretation
    (the value that defines tag ordering), and ``value`` is the exact opaque value bytes. Nested Roughtime
    messages inside ``value`` are never recursively interpreted in K1.
    """

    tag: bytes
    tag_uint32: int
    value: bytes


@dataclass(frozen=True)
class RoughtimeV19Message:
    """A parsed generic Roughtime message.

    ``fields`` are the ``pair_count`` tag/value pairs in canonical wire order and ``raw`` is the exact
    original message bytes.
    """

    pair_count: int
    fields: tuple[RoughtimeV19Field, ...]
    raw: bytes


@dataclass(frozen=True)
class RoughtimeV19Packet:
    """A parsed Roughtime outer packet: magic, declared message length, the parsed message, and raw bytes."""

    magic: bytes
    message_length: int
    message: RoughtimeV19Message
    raw: bytes


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


def parse_roughtime_v19_message(message_bytes: bytes) -> RoughtimeV19Message:
    """Parse and structurally validate a generic Roughtime draft-19 message.

    Accepts exact built-in ``bytes`` only. Every structural violation raises
    :class:`RoughtimeV19KernelError` with a closed :class:`RoughtimeV19KernelReason`. Values are preserved
    as exact opaque bytes; no tag is semantically interpreted.
    """
    if type(message_bytes) is not bytes:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.WRONG_INPUT_TYPE)

    length = len(message_bytes)
    if length > _MAX_MESSAGE_BYTES:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.MESSAGE_TOO_LARGE)
    if length < _MIN_MESSAGE_BYTES:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.MESSAGE_TOO_SHORT)

    pair_count = int.from_bytes(message_bytes[0:_UINT32_BYTES], "little")
    if pair_count < 1:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PAIR_COUNT_ZERO)
    if pair_count > _MAX_PAIR_COUNT:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PAIR_COUNT_EXCEEDS_LIMIT)

    # Header layout: one uint32 pair-count word, then N-1 offset words, then N tag words (== 8 * N bytes).
    count_field_bytes = _UINT32_BYTES
    offsets_bytes = (pair_count - 1) * _UINT32_BYTES
    tags_bytes = pair_count * _UINT32_BYTES
    header_length = count_field_bytes + offsets_bytes + tags_bytes
    if length < header_length:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.HEADER_TRUNCATED)

    values = message_bytes[header_length:]
    values_length = len(values)

    # Decode and validate the N-1 explicit offsets. The first value's offset is implicitly zero.
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

    # Decode and validate the N tags (canonical form first, then strict little-endian ordering).
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

    fields = []
    for index in range(pair_count):
        value = values[boundaries[index] : boundaries[index + 1]]
        fields.append(RoughtimeV19Field(tag=tags[index], tag_uint32=tag_values[index], value=value))

    return RoughtimeV19Message(pair_count=pair_count, fields=tuple(fields), raw=message_bytes)


def parse_roughtime_v19_packet(packet_bytes: bytes) -> RoughtimeV19Packet:
    """Parse and structurally validate a Roughtime draft-19 outer packet.

    Accepts exact built-in ``bytes`` only. Validates the magic and the declared message length, then parses
    the exact enclosed message bytes with :func:`parse_roughtime_v19_message`. Every structural violation
    raises :class:`RoughtimeV19KernelError` with a closed :class:`RoughtimeV19KernelReason`.
    """
    if type(packet_bytes) is not bytes:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.WRONG_INPUT_TYPE)

    length = len(packet_bytes)
    if length > _MAX_PACKET_BYTES:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PACKET_TOO_LARGE)
    if length < _MIN_PACKET_BYTES:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PACKET_TOO_SHORT)

    if packet_bytes[0:_MAGIC_LENGTH] != _ROUGHTIME_MAGIC:
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PACKET_MAGIC_MISMATCH)

    declared_length = int.from_bytes(packet_bytes[_MAGIC_LENGTH : _MAGIC_LENGTH + _LENGTH_FIELD_BYTES], "little")
    message_bytes = packet_bytes[_PACKET_FRAME_BYTES:]
    if declared_length != len(message_bytes):
        raise RoughtimeV19KernelError(RoughtimeV19KernelReason.PACKET_MESSAGE_LENGTH_MISMATCH)

    message = parse_roughtime_v19_message(message_bytes)
    return RoughtimeV19Packet(
        magic=_ROUGHTIME_MAGIC,
        message_length=declared_length,
        message=message,
        raw=packet_bytes,
    )


__all__ = [
    "RoughtimeV19Field",
    "RoughtimeV19KernelError",
    "RoughtimeV19KernelReason",
    "RoughtimeV19Message",
    "RoughtimeV19Packet",
    "parse_roughtime_v19_message",
    "parse_roughtime_v19_packet",
]
