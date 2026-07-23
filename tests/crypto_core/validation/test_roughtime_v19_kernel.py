"""Tests for the Roughtime draft-19 bounded structural kernel (internal MT-4 prerequisite K1).

All inputs are controller-owned deterministic synthetic bytes built by a small, auditable, test-only encoder
that never calls the production parsing logic. There is no real provider data, no captured packet, no
network, no filesystem fixture, no subprocess, no randomness, no time, and no cryptography. Boundary and
ordering expectations are constructed independently of the production module; production limit constants are
never imported to compute boundary payloads (they are only compared in explicit identity tests).

The kernel implements ONE governance-selected, versioned, bounded structural profile. Inputs that exceed a
profile limit are OUTSIDE THIS PROFILE, not proven malformed draft-19; the tests below assert exactly that
semantics and never describe an over-limit input as malformed.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError
from enum import Enum

import pytest

import crypto_core.validation.roughtime_v19_kernel as kernel_module
from crypto_core.validation.roughtime_v19_kernel import (
    RoughtimeV19Field,
    RoughtimeV19KernelError,
    RoughtimeV19KernelReason,
    RoughtimeV19Message,
    RoughtimeV19Packet,
    parse_roughtime_v19_message,
    parse_roughtime_v19_packet,
)

# --- Independently pinned contract values (not read from the production module) --------------------------
_MAGIC = b"ROUGHTIM"
_EXPECTED_PROFILE_ID = "roughtime-v19-structural-bounded-k1.v1"
_EXPECTED_MAX_PACKET_BYTES = 4096
_EXPECTED_MAX_MESSAGE_BYTES = 4084
_EXPECTED_MAX_PAIR_COUNT = 64
_ETHERNET_MTU = 1500  # a value that is well within the profile; valid draft-19 packets can exceed it

# Canonical valid tags in strictly ascending little-endian uint32 order.
_TAG_A = b"A\x00\x00\x00"  # le 0x00000041 = 65
_TAG_B = b"B\x00\x00\x00"  # le 0x00000042 = 66
_TAG_C = b"C\x00\x00\x00"  # le 0x00000043 = 67
_TAG_AB = b"AB\x00\x00"  # le 0x00004241 = 16961 (two letters)
_TAG_ABC = b"ABC\x00"  # three letters
_TAG_ABCD = b"ABCD"  # four letters
_TAG_ZZ = b"ZZ\x00\x00"  # structurally valid, semantically unknown

# Tags that expose little-endian vs byte-lexicographic ordering.
_TAG_BA_LE = b"BA\x00\x00"  # le 0x00004142 = 16706
_TAG_AB_LE = b"AB\x00\x00"  # le 0x00004241 = 16961


# --- Test-only encoder (independent of production parsing) ------------------------------------------------
def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "little")


def _le(tag: bytes) -> int:
    return int.from_bytes(tag, "little")


def _encode_message_raw(
    pair_count: int,
    offsets: list[int],
    tags: list[bytes],
    values_blob: bytes,
) -> bytes:
    """Assemble raw message bytes with full caller control (allows deliberately malformed inputs)."""
    parts = [_u32(pair_count)]
    parts.extend(_u32(offset) for offset in offsets)
    parts.extend(tags)
    parts.append(values_blob)
    return b"".join(parts)


def _encode_canonical_message(pairs: list[tuple[bytes, bytes]]) -> bytes:
    """Assemble a well-formed message from (tag, value) pairs already in intended wire order.

    Offsets are derived from cumulative value lengths, so each value length EXCEPT THE LAST must be a
    multiple of four (only the explicit offsets are four-byte aligned; the final value, which has no explicit
    offset, may be any length).
    """
    tags = [tag for tag, _ in pairs]
    values = [value for _, value in pairs]
    boundaries = [0]
    running = 0
    for value in values:
        running += len(value)
        boundaries.append(running)
    offsets = boundaries[1:-1]  # start positions of values 1..N-1
    return _encode_message_raw(len(pairs), offsets, tags, b"".join(values))


def _encode_packet(message_bytes: bytes, magic: bytes = _MAGIC, declared_length: int | None = None) -> bytes:
    if declared_length is None:
        declared_length = len(message_bytes)
    return magic + _u32(declared_length) + message_bytes


def _ascending_valid_tags(count: int) -> list[bytes]:
    """Return ``count`` canonical two-letter tags in strictly ascending little-endian order."""
    tags = [
        bytes([first, second, 0, 0])
        for first in range(0x41, 0x5B)  # "A".."Z"
        for second in range(0x41, 0x5B)  # "A".."Z"
    ]
    tags.sort(key=_le)
    return tags[:count]


def _assert_reason(func, argument, reason: RoughtimeV19KernelReason) -> None:
    with pytest.raises(RoughtimeV19KernelError) as exc_info:
        func(argument)
    assert exc_info.value.reason is reason


def _valid_message() -> RoughtimeV19Message:
    return parse_roughtime_v19_message(_encode_canonical_message([(_TAG_A, b""), (_TAG_B, b"\x01\x02\x03\x04")]))


def _valid_packet() -> RoughtimeV19Packet:
    message_bytes = _encode_canonical_message([(_TAG_A, b""), (_TAG_B, b"\x01\x02\x03\x04")])
    return parse_roughtime_v19_packet(_encode_packet(message_bytes))


# --- Encoder self-check ----------------------------------------------------------------------------------
def test_encoder_self_check_tag_ordering_assumptions() -> None:
    assert _le(_TAG_A) < _le(_TAG_B) < _le(_TAG_C) < _le(_TAG_AB) < _le(_TAG_ZZ)
    assert _le(_TAG_A) < _le(_TAG_AB) < _le(_TAG_ABC) < _le(_TAG_ABCD)
    assert _le(_TAG_BA_LE) < _le(_TAG_AB_LE)
    assert _TAG_AB_LE < _TAG_BA_LE  # byte-lexicographic order is the opposite


# --- Positive coverage -----------------------------------------------------------------------------------
def test_minimal_one_pair_message() -> None:
    message = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_A, b"")]))
    assert isinstance(message, RoughtimeV19Message)
    assert message.pair_count == 1
    assert message.fields[0].tag == _TAG_A
    assert message.fields[0].tag_uint32 == _le(_TAG_A)
    assert message.fields[0].value == b""


def test_zero_length_value_accepted() -> None:
    message = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_A, b""), (_TAG_B, b"\x01\x02\x03\x04")]))
    assert message.fields[0].value == b""
    assert message.fields[1].value == b"\x01\x02\x03\x04"


def test_multiple_sorted_tags_accepted() -> None:
    message = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_A, b""), (_TAG_B, b""), (_TAG_C, b"")]))
    assert message.pair_count == 3
    assert [field.tag for field in message.fields] == [_TAG_A, _TAG_B, _TAG_C]


def test_multiple_values_preserved_in_order() -> None:
    pairs = [
        (_TAG_A, b"\xaa\xbb\xcc\xdd"),
        (_TAG_B, b""),
        (_TAG_C, b"\x11\x22\x33\x44\x55\x66\x77\x88"),
    ]
    message = parse_roughtime_v19_message(_encode_canonical_message(pairs))
    assert [field.value for field in message.fields] == [value for _, value in pairs]


def test_equal_adjacent_offsets_accepted() -> None:
    pairs = [(_TAG_A, b""), (_TAG_B, b""), (_TAG_C, b"\x00\x00\x00\x00")]
    message = parse_roughtime_v19_message(_encode_canonical_message(pairs))
    assert [len(field.value) for field in message.fields] == [0, 0, 4]


def test_unknown_valid_tag_accepted() -> None:
    message = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_ZZ, b"")]))
    assert message.fields[0].tag == _TAG_ZZ


def test_three_letter_tag_accepted() -> None:
    message = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_ABC, b"")]))
    assert message.fields[0].tag == _TAG_ABC


def test_four_letter_tag_accepted() -> None:
    message = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_ABCD, b"")]))
    assert message.fields[0].tag == _TAG_ABCD


def test_mixed_length_tags_in_little_endian_order_accepted() -> None:
    pairs = [(_TAG_A, b""), (_TAG_AB, b""), (_TAG_ABC, b""), (_TAG_ABCD, b"")]
    message = parse_roughtime_v19_message(_encode_canonical_message(pairs))
    assert [field.tag for field in message.fields] == [_TAG_A, _TAG_AB, _TAG_ABC, _TAG_ABCD]
    values = [field.tag_uint32 for field in message.fields]
    assert values == sorted(values)


@pytest.mark.parametrize("final_length", [1, 2, 3, 5])
def test_arbitrary_final_value_length_accepted(final_length: int) -> None:
    # Only explicit offsets must be four-byte aligned; the final value (no explicit offset) may be any length.
    pairs = [(_TAG_A, b"\x00\x00\x00\x00"), (_TAG_B, b"\x11" * final_length)]
    message = parse_roughtime_v19_message(_encode_canonical_message(pairs))
    assert len(message.fields[1].value) == final_length
    assert message.fields[1].value == b"\x11" * final_length


def test_little_endian_tag_ordering_accepted() -> None:
    message = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_BA_LE, b""), (_TAG_AB_LE, b"")]))
    assert [field.tag for field in message.fields] == [_TAG_BA_LE, _TAG_AB_LE]
    assert message.fields[0].tag_uint32 < message.fields[1].tag_uint32


def test_valid_outer_packet_accepted() -> None:
    message_bytes = _encode_canonical_message([(_TAG_A, b""), (_TAG_B, b"\x01\x02\x03\x04")])
    packet = parse_roughtime_v19_packet(_encode_packet(message_bytes))
    assert isinstance(packet, RoughtimeV19Packet)
    assert packet.magic == _MAGIC
    assert packet.message_length == len(message_bytes)
    assert packet.message.pair_count == 2


def test_valid_packet_above_ethernet_mtu_accepted() -> None:
    # A structurally valid draft-19 packet larger than the Ethernet MTU (but within the bounded profile).
    message_bytes = _u32(1) + _TAG_A + b"\x00" * _ETHERNET_MTU
    packet_bytes = _encode_packet(message_bytes)
    assert len(packet_bytes) > _ETHERNET_MTU
    assert len(packet_bytes) <= _EXPECTED_MAX_PACKET_BYTES
    packet = parse_roughtime_v19_packet(packet_bytes)
    assert len(packet.message.fields[0].value) == _ETHERNET_MTU


def test_deterministic_repeated_parse() -> None:
    message_bytes = _encode_canonical_message([(_TAG_A, b"\x01\x02\x03\x04"), (_TAG_B, b"")])
    assert parse_roughtime_v19_message(message_bytes) == parse_roughtime_v19_message(message_bytes)
    packet_bytes = _encode_packet(message_bytes)
    assert parse_roughtime_v19_packet(packet_bytes) == parse_roughtime_v19_packet(packet_bytes)


def test_parser_outputs_are_immutable() -> None:
    message = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_A, b"")]))
    assert isinstance(message.fields, tuple)
    with pytest.raises(FrozenInstanceError):
        message.pair_count = 99  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        message.fields[0].tag = b"XXXX"  # type: ignore[misc]


def test_exact_raw_message_preservation() -> None:
    message_bytes = _encode_canonical_message([(_TAG_A, b"\x01\x02\x03\x04"), (_TAG_B, b"")])
    message = parse_roughtime_v19_message(message_bytes)
    assert message.raw == message_bytes


def test_exact_raw_packet_preservation() -> None:
    message_bytes = _encode_canonical_message([(_TAG_A, b"\x01\x02\x03\x04")])
    packet_bytes = _encode_packet(message_bytes)
    packet = parse_roughtime_v19_packet(packet_bytes)
    assert packet.raw == packet_bytes
    assert packet.message.raw == message_bytes


# --- Negative: input trust boundary ----------------------------------------------------------------------
class _BytesSubclass(bytes):
    pass


_VALID_PACKET_BYTES = _encode_packet(_encode_canonical_message([(_TAG_A, b"")]))
_VALID_MESSAGE_BYTES = _encode_canonical_message([(_TAG_A, b"")])


@pytest.mark.parametrize(
    "bad_input",
    [
        bytearray(_VALID_PACKET_BYTES),
        memoryview(_VALID_PACKET_BYTES),
        _BytesSubclass(_VALID_PACKET_BYTES),
        "ROUGHTIM",
        1234,
        None,
        [1, 2, 3],
        {"a": 1},
    ],
)
def test_packet_rejects_non_exact_bytes(bad_input: object) -> None:
    _assert_reason(parse_roughtime_v19_packet, bad_input, RoughtimeV19KernelReason.WRONG_INPUT_TYPE)


@pytest.mark.parametrize(
    "bad_input",
    [
        bytearray(_VALID_MESSAGE_BYTES),
        memoryview(_VALID_MESSAGE_BYTES),
        _BytesSubclass(_VALID_MESSAGE_BYTES),
        "AAAA",
        1234,
        None,
        [1, 2, 3],
        {"a": 1},
    ],
)
def test_message_rejects_non_exact_bytes(bad_input: object) -> None:
    _assert_reason(parse_roughtime_v19_message, bad_input, RoughtimeV19KernelReason.WRONG_INPUT_TYPE)


# --- Negative: packet framing ----------------------------------------------------------------------------
def test_packet_shorter_than_frame_rejected() -> None:
    _assert_reason(parse_roughtime_v19_packet, b"ROUGHTIM\x00\x00", RoughtimeV19KernelReason.PACKET_TOO_SHORT)


def test_packet_wrong_magic_rejected() -> None:
    packet_bytes = b"ROUGHXXX" + _u32(len(_VALID_MESSAGE_BYTES)) + _VALID_MESSAGE_BYTES
    _assert_reason(parse_roughtime_v19_packet, packet_bytes, RoughtimeV19KernelReason.PACKET_MAGIC_MISMATCH)


def test_packet_declared_length_too_small_rejected() -> None:
    packet_bytes = _encode_packet(_VALID_MESSAGE_BYTES, declared_length=len(_VALID_MESSAGE_BYTES) - 4)
    _assert_reason(parse_roughtime_v19_packet, packet_bytes, RoughtimeV19KernelReason.PACKET_MESSAGE_LENGTH_MISMATCH)


def test_packet_declared_length_too_large_rejected() -> None:
    packet_bytes = _encode_packet(_VALID_MESSAGE_BYTES, declared_length=len(_VALID_MESSAGE_BYTES) + 4)
    _assert_reason(parse_roughtime_v19_packet, packet_bytes, RoughtimeV19KernelReason.PACKET_MESSAGE_LENGTH_MISMATCH)


def test_packet_trailing_bytes_rejected() -> None:
    packet_bytes = _encode_packet(_VALID_MESSAGE_BYTES, declared_length=len(_VALID_MESSAGE_BYTES)) + b"\x00\x00\x00\x00"
    _assert_reason(parse_roughtime_v19_packet, packet_bytes, RoughtimeV19KernelReason.PACKET_MESSAGE_LENGTH_MISMATCH)


# --- Negative: message framing ---------------------------------------------------------------------------
def test_message_fewer_than_four_bytes_rejected() -> None:
    _assert_reason(parse_roughtime_v19_message, b"\x00\x00\x00", RoughtimeV19KernelReason.MESSAGE_TOO_SHORT)


def test_message_pair_count_zero_rejected() -> None:
    _assert_reason(parse_roughtime_v19_message, _u32(0), RoughtimeV19KernelReason.PAIR_COUNT_ZERO)


def test_message_truncated_header_rejected() -> None:
    truncated = _u32(2) + _u32(0) + _TAG_A
    _assert_reason(parse_roughtime_v19_message, truncated, RoughtimeV19KernelReason.HEADER_TRUNCATED)


def test_message_missing_offset_rejected() -> None:
    missing_offset = _u32(2) + _TAG_A + _TAG_B
    _assert_reason(parse_roughtime_v19_message, missing_offset, RoughtimeV19KernelReason.HEADER_TRUNCATED)


def test_message_missing_tag_rejected() -> None:
    missing_tag = _u32(2) + _u32(0) + _TAG_A
    _assert_reason(parse_roughtime_v19_message, missing_tag, RoughtimeV19KernelReason.HEADER_TRUNCATED)


# --- Negative: offsets -----------------------------------------------------------------------------------
def test_offset_unaligned_rejected() -> None:
    raw = _encode_message_raw(2, [2], [_TAG_A, _TAG_B], b"\x00\x00\x00\x00")
    _assert_reason(parse_roughtime_v19_message, raw, RoughtimeV19KernelReason.OFFSET_UNALIGNED)


def test_offset_descending_rejected() -> None:
    raw = _encode_message_raw(3, [8, 4], [_TAG_A, _TAG_B, _TAG_C], b"\x00" * 8)
    _assert_reason(parse_roughtime_v19_message, raw, RoughtimeV19KernelReason.OFFSET_ORDER_INVALID)


def test_offset_out_of_bounds_rejected() -> None:
    raw = _encode_message_raw(2, [8], [_TAG_A, _TAG_B], b"\x00\x00\x00\x00")
    _assert_reason(parse_roughtime_v19_message, raw, RoughtimeV19KernelReason.OFFSET_OUT_OF_BOUNDS)


def test_final_explicit_offset_out_of_bounds_rejected() -> None:
    raw = _encode_message_raw(3, [4, 100], [_TAG_A, _TAG_B, _TAG_C], b"\x00" * 8)
    _assert_reason(parse_roughtime_v19_message, raw, RoughtimeV19KernelReason.OFFSET_OUT_OF_BOUNDS)


# --- Negative: tags --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tag",
    [
        b"\x00\x00\x00\x00",  # all zero
        b"abcd",  # lowercase
        b"1234",  # digits
        b"!@#$",  # punctuation
        b"A\x00B\x00",  # nonzero byte after zero padding
        b"\x00AAA",  # leading zero
    ],
)
def test_invalid_tag_rejected(tag: bytes) -> None:
    raw = _encode_message_raw(1, [], [tag], b"")
    _assert_reason(parse_roughtime_v19_message, raw, RoughtimeV19KernelReason.TAG_INVALID)


def test_duplicate_tag_rejected() -> None:
    raw = _encode_message_raw(2, [0], [_TAG_A, _TAG_A], b"")
    _assert_reason(parse_roughtime_v19_message, raw, RoughtimeV19KernelReason.TAG_DUPLICATE)


def test_unsorted_tags_rejected() -> None:
    raw = _encode_message_raw(2, [0], [_TAG_B, _TAG_A], b"")
    _assert_reason(parse_roughtime_v19_message, raw, RoughtimeV19KernelReason.TAG_ORDER_INVALID)


def test_unsorted_little_endian_numeric_order_rejected() -> None:
    raw = _encode_message_raw(2, [0], [_TAG_AB_LE, _TAG_BA_LE], b"")
    _assert_reason(parse_roughtime_v19_message, raw, RoughtimeV19KernelReason.TAG_ORDER_INVALID)


def test_non_adjacent_duplicate_surfaces_as_order_invalid() -> None:
    # Tags [A, B, A]: A < B, then A < B again is the first DESCENDING relationship (B -> A). Strict
    # wire-order validation reaches that descent before the non-adjacent A/A pair could be treated as an
    # adjacent duplicate, so the deterministic precedence is TAG_ORDER_INVALID (not normalization).
    raw = _encode_message_raw(3, [0, 0], [_TAG_A, _TAG_B, _TAG_A], b"")
    _assert_reason(parse_roughtime_v19_message, raw, RoughtimeV19KernelReason.TAG_ORDER_INVALID)


# --- Bounded-profile limits (OUTSIDE PROFILE, not malformed) ---------------------------------------------
def test_packet_size_boundary_first_accepted_and_first_outside_profile() -> None:
    message_bytes = _u32(1) + _TAG_A + b"\x00" * (_EXPECTED_MAX_MESSAGE_BYTES - 8)
    packet_bytes = _encode_packet(message_bytes)
    assert len(packet_bytes) == _EXPECTED_MAX_PACKET_BYTES
    accepted = parse_roughtime_v19_packet(packet_bytes)
    assert accepted.message.pair_count == 1
    # One byte larger is OUTSIDE THIS PROFILE (not malformed Roughtime).
    _assert_reason(
        parse_roughtime_v19_packet, packet_bytes + b"\x00", RoughtimeV19KernelReason.PROFILE_PACKET_BYTES_EXCEEDED
    )


def test_message_size_boundary_first_accepted_and_first_outside_profile() -> None:
    accepted_bytes = _u32(1) + _TAG_A + b"\x00" * (_EXPECTED_MAX_MESSAGE_BYTES - 8)
    assert len(accepted_bytes) == _EXPECTED_MAX_MESSAGE_BYTES
    accepted = parse_roughtime_v19_message(accepted_bytes)
    assert accepted.pair_count == 1
    # One byte larger is OUTSIDE THIS PROFILE (not malformed Roughtime).
    _assert_reason(
        parse_roughtime_v19_message, accepted_bytes + b"\x00", RoughtimeV19KernelReason.PROFILE_MESSAGE_BYTES_EXCEEDED
    )


def test_pair_count_boundary_first_accepted_and_first_outside_profile() -> None:
    tags = _ascending_valid_tags(_EXPECTED_MAX_PAIR_COUNT)
    accepted = parse_roughtime_v19_message(_encode_canonical_message([(tag, b"") for tag in tags]))
    assert accepted.pair_count == _EXPECTED_MAX_PAIR_COUNT
    _assert_reason(
        parse_roughtime_v19_message,
        _u32(_EXPECTED_MAX_PAIR_COUNT + 1),
        RoughtimeV19KernelReason.PROFILE_PAIR_COUNT_EXCEEDED,
    )


def test_structurally_valid_message_one_byte_over_profile_is_outside_profile_not_malformed() -> None:
    # A message that is well-formed except that it is one byte over the profile ceiling.
    over_bytes = _u32(1) + _TAG_A + b"\x00" * (_EXPECTED_MAX_MESSAGE_BYTES - 8 + 1)
    assert len(over_bytes) == _EXPECTED_MAX_MESSAGE_BYTES + 1
    _assert_reason(parse_roughtime_v19_message, over_bytes, RoughtimeV19KernelReason.PROFILE_MESSAGE_BYTES_EXCEEDED)


def test_structurally_valid_packet_one_byte_over_profile_is_outside_profile_not_malformed() -> None:
    inner = _u32(1) + _TAG_A + b"\x00" * (_EXPECTED_MAX_MESSAGE_BYTES - 8 + 1)
    over_packet = _encode_packet(inner)
    assert len(over_packet) == _EXPECTED_MAX_PACKET_BYTES + 1
    _assert_reason(parse_roughtime_v19_packet, over_packet, RoughtimeV19KernelReason.PROFILE_PACKET_BYTES_EXCEEDED)


def test_structurally_valid_message_over_pair_count_is_outside_profile_not_malformed() -> None:
    # A fully well-formed 65-pair message (empty values); rejected only because 65 is over the profile.
    over_pairs = [(tag, b"") for tag in _ascending_valid_tags(_EXPECTED_MAX_PAIR_COUNT + 1)]
    over_bytes = _encode_canonical_message(over_pairs)
    _assert_reason(parse_roughtime_v19_message, over_bytes, RoughtimeV19KernelReason.PROFILE_PAIR_COUNT_EXCEEDED)


# --- Contract pinning ------------------------------------------------------------------------------------
def test_profile_identity_and_limits_pinned() -> None:
    assert kernel_module.ROUGHTIME_V19_STRUCTURAL_PROFILE_ID == _EXPECTED_PROFILE_ID
    assert kernel_module.ROUGHTIME_V19_MAX_PACKET_BYTES == _EXPECTED_MAX_PACKET_BYTES
    assert kernel_module.ROUGHTIME_V19_MAX_MESSAGE_BYTES == _EXPECTED_MAX_MESSAGE_BYTES
    assert kernel_module.ROUGHTIME_V19_MAX_PAIR_COUNT == _EXPECTED_MAX_PAIR_COUNT
    assert kernel_module.ROUGHTIME_V19_MAX_MESSAGE_BYTES == _EXPECTED_MAX_PACKET_BYTES - 12


def test_reason_name_value_mapping_is_pinned() -> None:
    expected = {
        "WRONG_INPUT_TYPE": "wrong_input_type",
        "PACKET_TOO_SHORT": "packet_too_short",
        "PROFILE_PACKET_BYTES_EXCEEDED": "profile_packet_bytes_exceeded",
        "PACKET_MAGIC_MISMATCH": "packet_magic_mismatch",
        "PACKET_MESSAGE_LENGTH_MISMATCH": "packet_message_length_mismatch",
        "MESSAGE_TOO_SHORT": "message_too_short",
        "PROFILE_MESSAGE_BYTES_EXCEEDED": "profile_message_bytes_exceeded",
        "PAIR_COUNT_ZERO": "pair_count_zero",
        "PROFILE_PAIR_COUNT_EXCEEDED": "profile_pair_count_exceeded",
        "HEADER_TRUNCATED": "header_truncated",
        "OFFSET_UNALIGNED": "offset_unaligned",
        "OFFSET_ORDER_INVALID": "offset_order_invalid",
        "OFFSET_OUT_OF_BOUNDS": "offset_out_of_bounds",
        "TAG_INVALID": "tag_invalid",
        "TAG_ORDER_INVALID": "tag_order_invalid",
        "TAG_DUPLICATE": "tag_duplicate",
        "ARTIFACT_FIELD_INCONSISTENT": "artifact_field_inconsistent",
        "ARTIFACT_MESSAGE_INCONSISTENT": "artifact_message_inconsistent",
        "ARTIFACT_PACKET_INCONSISTENT": "artifact_packet_inconsistent",
    }
    actual = {member.name: member.value for member in RoughtimeV19KernelReason}
    assert actual == expected
    values = list(actual.values())
    assert len(values) == len(set(values))
    assert all(value == value.lower() for value in values)


def test_public_api_names_exact() -> None:
    expected = {
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
    }
    assert set(kernel_module.__all__) == expected
    for name in expected:
        assert hasattr(kernel_module, name)


# --- Hardened error constructor (P2-2) -------------------------------------------------------------------
class _ForeignReason(str, Enum):
    WRONG_INPUT_TYPE = "wrong_input_type"


class _RaisingValue:
    @property
    def value(self) -> str:
        raise RuntimeError("hostile .value must never be accessed")


class _RecordingValue:
    def __init__(self) -> None:
        self.accessed = False

    @property
    def value(self) -> str:
        self.accessed = True
        return "wrong_input_type"


@pytest.mark.parametrize(
    "bad_reason",
    [
        "wrong_input_type",
        0,
        1,
        None,
        _ForeignReason.WRONG_INPUT_TYPE,
        RoughtimeV19KernelReason.WRONG_INPUT_TYPE.value,
    ],
)
def test_error_constructor_rejects_non_exact_reason(bad_reason: object) -> None:
    with pytest.raises(TypeError):
        RoughtimeV19KernelError(bad_reason)  # type: ignore[arg-type]


def test_error_constructor_type_message_is_fixed() -> None:
    with pytest.raises(TypeError) as exc_info:
        RoughtimeV19KernelError("nope")  # type: ignore[arg-type]
    assert str(exc_info.value) == "RoughtimeV19KernelError requires a RoughtimeV19KernelReason member"


def test_error_constructor_never_touches_hostile_value_that_raises() -> None:
    with pytest.raises(TypeError):
        RoughtimeV19KernelError(_RaisingValue())  # type: ignore[arg-type]


def test_error_constructor_never_accesses_hostile_value_property() -> None:
    hostile = _RecordingValue()
    with pytest.raises(TypeError):
        RoughtimeV19KernelError(hostile)  # type: ignore[arg-type]
    assert hostile.accessed is False


def test_error_accepts_exact_reason_and_str_is_value() -> None:
    error = RoughtimeV19KernelError(RoughtimeV19KernelReason.TAG_INVALID)
    assert error.reason is RoughtimeV19KernelReason.TAG_INVALID
    assert str(error) == "tag_invalid"
    assert error.args == ("tag_invalid",)


def test_error_reason_is_immutable() -> None:
    error = RoughtimeV19KernelError(RoughtimeV19KernelReason.TAG_INVALID)
    with pytest.raises(AttributeError):
        error.reason = RoughtimeV19KernelReason.TAG_DUPLICATE  # type: ignore[misc]
    with pytest.raises(AttributeError):
        error._reason = RoughtimeV19KernelReason.TAG_DUPLICATE
    with pytest.raises(AttributeError):
        error.args = ("forged",)
    with pytest.raises(AttributeError):
        del error.reason
    assert error.reason is RoughtimeV19KernelReason.TAG_INVALID
    assert str(error) == "tag_invalid"


# --- Self-validating artifacts (P2-3): Field -------------------------------------------------------------
def _assert_field_inconsistent(**kwargs: object) -> None:
    with pytest.raises(RoughtimeV19KernelError) as exc_info:
        RoughtimeV19Field(**kwargs)  # type: ignore[arg-type]
    assert exc_info.value.reason is RoughtimeV19KernelReason.ARTIFACT_FIELD_INCONSISTENT


def test_field_non_bytes_tag_rejected() -> None:
    _assert_field_inconsistent(tag="AAAA", tag_uint32=0, value=b"")


def test_field_wrong_tag_length_rejected() -> None:
    _assert_field_inconsistent(tag=b"AAA", tag_uint32=_le(b"AAA\x00"), value=b"")


def test_field_invalid_tag_rejected() -> None:
    _assert_field_inconsistent(tag=b"aaaa", tag_uint32=_le(b"aaaa"), value=b"")


def test_field_inconsistent_tag_integer_rejected() -> None:
    _assert_field_inconsistent(tag=_TAG_A, tag_uint32=999, value=b"")


def test_field_bool_integer_rejected() -> None:
    _assert_field_inconsistent(tag=_TAG_A, tag_uint32=True, value=b"")


def test_field_non_bytes_value_rejected() -> None:
    _assert_field_inconsistent(tag=_TAG_A, tag_uint32=_le(_TAG_A), value="")


def test_field_mutable_value_rejected() -> None:
    _assert_field_inconsistent(tag=_TAG_A, tag_uint32=_le(_TAG_A), value=bytearray(b"\x00"))


def test_field_bytes_subclass_tag_rejected() -> None:
    _assert_field_inconsistent(tag=_BytesSubclass(_TAG_A), tag_uint32=_le(_TAG_A), value=b"")


def test_valid_field_constructs() -> None:
    field = RoughtimeV19Field(tag=_TAG_A, tag_uint32=_le(_TAG_A), value=b"\x00\x00\x00\x00")
    assert field.value == b"\x00\x00\x00\x00"


# --- Self-validating artifacts (P2-3): Message -----------------------------------------------------------
class _TupleSubclass(tuple):
    pass


class _FieldSubclass(RoughtimeV19Field):
    pass


def _assert_message_inconsistent(**kwargs: object) -> None:
    with pytest.raises(RoughtimeV19KernelError) as exc_info:
        RoughtimeV19Message(**kwargs)  # type: ignore[arg-type]
    assert exc_info.value.reason is RoughtimeV19KernelReason.ARTIFACT_MESSAGE_INCONSISTENT


def test_message_pair_count_mismatch_rejected() -> None:
    base = _valid_message()
    _assert_message_inconsistent(pair_count=3, fields=base.fields, raw=base.raw)


def test_message_bool_pair_count_rejected() -> None:
    base = _valid_message()
    _assert_message_inconsistent(pair_count=True, fields=base.fields, raw=base.raw)


def test_message_list_instead_of_tuple_rejected() -> None:
    base = _valid_message()
    _assert_message_inconsistent(pair_count=base.pair_count, fields=list(base.fields), raw=base.raw)


def test_message_tuple_subclass_rejected() -> None:
    base = _valid_message()
    _assert_message_inconsistent(pair_count=base.pair_count, fields=_TupleSubclass(base.fields), raw=base.raw)


def test_message_foreign_field_rejected() -> None:
    _assert_message_inconsistent(pair_count=1, fields=(object(),), raw=_VALID_MESSAGE_BYTES)


def test_message_field_subclass_rejected() -> None:
    sub = _FieldSubclass(tag=_TAG_A, tag_uint32=_le(_TAG_A), value=b"")
    _assert_message_inconsistent(pair_count=1, fields=(sub,), raw=_VALID_MESSAGE_BYTES)


def test_message_non_bytes_raw_rejected() -> None:
    base = _valid_message()
    _assert_message_inconsistent(pair_count=base.pair_count, fields=base.fields, raw=bytearray(base.raw))


def test_message_raw_fields_mismatch_rejected() -> None:
    donor = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_A, b""), (_TAG_B, b"\xff\xff\xff\xff")]))
    base = _valid_message()
    _assert_message_inconsistent(pair_count=base.pair_count, fields=base.fields, raw=donor.raw)


def test_message_reordered_fields_rejected() -> None:
    base = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_A, b""), (_TAG_B, b""), (_TAG_C, b"")]))
    reordered = (base.fields[2], base.fields[1], base.fields[0])
    _assert_message_inconsistent(pair_count=3, fields=reordered, raw=base.raw)


def test_message_altered_value_rejected() -> None:
    base = _valid_message()
    altered = RoughtimeV19Field(tag=base.fields[1].tag, tag_uint32=base.fields[1].tag_uint32, value=b"\xff\xff\xff\xff")
    _assert_message_inconsistent(pair_count=2, fields=(base.fields[0], altered), raw=base.raw)


def test_valid_message_direct_construction_round_trips() -> None:
    parsed = _valid_message()
    rebuilt = RoughtimeV19Message(pair_count=parsed.pair_count, fields=parsed.fields, raw=parsed.raw)
    assert rebuilt == parsed


# --- Self-validating artifacts (P2-3): Packet ------------------------------------------------------------
class _MessageSubclass(RoughtimeV19Message):
    pass


def _assert_packet_inconsistent(**kwargs: object) -> None:
    with pytest.raises(RoughtimeV19KernelError) as exc_info:
        RoughtimeV19Packet(**kwargs)  # type: ignore[arg-type]
    assert exc_info.value.reason is RoughtimeV19KernelReason.ARTIFACT_PACKET_INCONSISTENT


def test_packet_wrong_magic_direct_rejected() -> None:
    base = _valid_packet()
    _assert_packet_inconsistent(
        magic=b"XXXXXXXX", message_length=base.message_length, message=base.message, raw=base.raw
    )


def test_packet_non_bytes_magic_rejected() -> None:
    base = _valid_packet()
    _assert_packet_inconsistent(
        magic="ROUGHTIM", message_length=base.message_length, message=base.message, raw=base.raw
    )


def test_packet_bool_message_length_rejected() -> None:
    base = _valid_packet()
    _assert_packet_inconsistent(magic=base.magic, message_length=True, message=base.message, raw=base.raw)


def test_packet_incorrect_message_length_rejected() -> None:
    base = _valid_packet()
    _assert_packet_inconsistent(
        magic=base.magic, message_length=base.message_length + 4, message=base.message, raw=base.raw
    )


def test_packet_forged_message_rejected() -> None:
    base = _valid_packet()
    _assert_packet_inconsistent(magic=base.magic, message_length=base.message_length, message=object(), raw=base.raw)


def test_packet_message_subclass_rejected() -> None:
    base = _valid_packet()
    sub = _MessageSubclass(pair_count=base.message.pair_count, fields=base.message.fields, raw=base.message.raw)
    _assert_packet_inconsistent(magic=base.magic, message_length=base.message_length, message=sub, raw=base.raw)


def test_packet_non_bytes_raw_rejected() -> None:
    base = _valid_packet()
    _assert_packet_inconsistent(
        magic=base.magic, message_length=base.message_length, message=base.message, raw=bytearray(base.raw)
    )


def test_packet_raw_message_mismatch_rejected() -> None:
    donor_msg = _encode_canonical_message([(_TAG_A, b""), (_TAG_B, b"\xff\xff\xff\xff")])
    donor = parse_roughtime_v19_packet(_encode_packet(donor_msg))
    base = _valid_packet()
    # raw is the donor packet (different embedded message); message is base's message.
    _assert_packet_inconsistent(
        magic=base.magic, message_length=donor.message_length, message=base.message, raw=donor.raw
    )


def test_packet_nested_raw_mismatch_rejected() -> None:
    donor_msg = _encode_canonical_message([(_TAG_A, b""), (_TAG_B, b"\xff\xff\xff\xff")])
    donor = parse_roughtime_v19_packet(_encode_packet(donor_msg))
    base = _valid_packet()
    # raw is base's packet; message is the donor's message (its raw differs from base's embedded bytes).
    _assert_packet_inconsistent(
        magic=base.magic, message_length=base.message_length, message=donor.message, raw=base.raw
    )


def test_packet_raw_declared_length_mismatch_rejected() -> None:
    base = _valid_packet()
    _assert_packet_inconsistent(
        magic=base.magic, message_length=base.message_length + 4, message=base.message, raw=base.raw
    )


def test_valid_packet_direct_construction_round_trips() -> None:
    parsed = _valid_packet()
    rebuilt = RoughtimeV19Packet(
        magic=parsed.magic, message_length=parsed.message_length, message=parsed.message, raw=parsed.raw
    )
    assert rebuilt == parsed


def test_no_forged_message_can_misrepresent_its_raw_bytes() -> None:
    # Any artifact whose supplied fields differ from a primitive re-decode of its raw bytes is rejected.
    base = _valid_message()
    swapped = RoughtimeV19Field(tag=base.fields[0].tag, tag_uint32=base.fields[0].tag_uint32, value=b"\x01\x02\x03\x04")
    _assert_message_inconsistent(pair_count=2, fields=(swapped, base.fields[1]), raw=base.raw)


# --- AST / structural safety -----------------------------------------------------------------------------
_ALLOWED_IMPORT_ROOTS = {"__future__", "dataclasses", "enum"}

_FORBIDDEN_SOURCE_TOKENS = (
    "cloudflare",
    "deribit",
    "binance",
    "coinbase",
    "kraken",
    "bybit",
    "okx",
    "borsa",
    "matriks",
    "machine_time_source_registry",
    "machine_time_anchor_evidence",
    "ed25519",
    "curve25519",
    "secp256k1",
    "order_router",
    "place_order",
    "socket",
    "subprocess",
)

_FORBIDDEN_CALL_NAMES = {"eval", "exec", "compile", "__import__", "open", "input"}


def _production_source() -> str:
    return inspect.getsource(kernel_module)


def test_production_imports_are_allowlisted() -> None:
    tree = ast.parse(_production_source())
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative imports permitted"
            if node.module:
                roots.add(node.module.split(".")[0])
    assert roots <= _ALLOWED_IMPORT_ROOTS, roots


def test_production_has_no_provider_or_leakage_tokens() -> None:
    lowered = _production_source().lower()
    present = [token for token in _FORBIDDEN_SOURCE_TOKENS if token in lowered]
    assert present == [], present


def test_production_has_no_dynamic_or_io_calls() -> None:
    tree = ast.parse(_production_source())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALL_NAMES:
            found.add(node.func.id)
    assert found == set(), found
