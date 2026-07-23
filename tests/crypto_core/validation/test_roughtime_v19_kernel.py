"""Tests for the Roughtime draft-19 structural kernel (internal MT-4 prerequisite K1).

All inputs are controller-owned deterministic synthetic bytes built by a small, auditable, test-only
encoder that never calls the production parsing logic. There is no real provider data, no captured packet,
no network, no filesystem fixture, no subprocess, no randomness, no time, and no cryptography. Boundary and
ordering expectations are constructed independently of the production module.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError

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
_EXPECTED_MAX_PACKET_BYTES = 1500
_EXPECTED_MAX_MESSAGE_BYTES = 1488
_EXPECTED_MAX_PAIR_COUNT = 64

# Canonical valid tags in strictly ascending little-endian uint32 order.
_TAG_A = b"A\x00\x00\x00"  # le 0x00000041 = 65
_TAG_B = b"B\x00\x00\x00"  # le 0x00000042 = 66
_TAG_C = b"C\x00\x00\x00"  # le 0x00000043 = 67
_TAG_AB = b"AB\x00\x00"  # le 0x00004241 = 16961
_TAG_ZZ = b"ZZ\x00\x00"  # le 0x00005a5a = 23130 — structurally valid, semantically unknown

# Tags that expose little-endian vs byte-lexicographic ordering: "BA.." is numerically < "AB.." because the
# low-order byte is compared first (B=0x42 low for "BA.." vs A=0x41 low for "AB..").
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

    Offsets are derived from value lengths, so every value length must be four-byte aligned for the result
    to be structurally valid.
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


# --- Encoder self-check (proves the encoder itself is sound before it is trusted) ------------------------
def test_encoder_self_check_tag_ordering_assumptions() -> None:
    assert _le(_TAG_A) < _le(_TAG_B) < _le(_TAG_C) < _le(_TAG_AB) < _le(_TAG_ZZ)
    # Little-endian numeric order is the reverse of the byte-lexicographic order for this pair.
    assert _le(_TAG_BA_LE) < _le(_TAG_AB_LE)
    assert _TAG_AB_LE < _TAG_BA_LE  # byte-lexicographic order is the opposite


# --- Positive coverage -----------------------------------------------------------------------------------
def test_minimal_one_pair_message() -> None:
    message = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_A, b"")]))
    assert isinstance(message, RoughtimeV19Message)
    assert message.pair_count == 1
    assert len(message.fields) == 1
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
    # Two adjacent zero-length values produce equal adjacent offsets.
    pairs = [(_TAG_A, b""), (_TAG_B, b""), (_TAG_C, b"\x00\x00\x00\x00")]
    message = parse_roughtime_v19_message(_encode_canonical_message(pairs))
    assert [len(field.value) for field in message.fields] == [0, 0, 4]


def test_unknown_valid_tag_accepted() -> None:
    message = parse_roughtime_v19_message(_encode_canonical_message([(_TAG_ZZ, b"")]))
    assert message.fields[0].tag == _TAG_ZZ


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
    assert isinstance(packet.message, RoughtimeV19Message)


def test_deterministic_repeated_parse() -> None:
    message_bytes = _encode_canonical_message([(_TAG_A, b"\x01\x02\x03\x04"), (_TAG_B, b"")])
    assert parse_roughtime_v19_message(message_bytes) == parse_roughtime_v19_message(message_bytes)
    packet_bytes = _encode_packet(message_bytes)
    assert parse_roughtime_v19_packet(packet_bytes) == parse_roughtime_v19_packet(packet_bytes)


def test_outputs_are_immutable() -> None:
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


_VALID_PACKET = _encode_packet(_encode_canonical_message([(_TAG_A, b"")]))
_VALID_MESSAGE = _encode_canonical_message([(_TAG_A, b"")])


@pytest.mark.parametrize(
    "bad_input",
    [
        bytearray(_VALID_PACKET),
        memoryview(_VALID_PACKET),
        _BytesSubclass(_VALID_PACKET),
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
        bytearray(_VALID_MESSAGE),
        memoryview(_VALID_MESSAGE),
        _BytesSubclass(_VALID_MESSAGE),
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
    packet_bytes = b"ROUGHXXX" + _u32(len(_VALID_MESSAGE)) + _VALID_MESSAGE
    _assert_reason(parse_roughtime_v19_packet, packet_bytes, RoughtimeV19KernelReason.PACKET_MAGIC_MISMATCH)


def test_packet_declared_length_too_small_rejected() -> None:
    packet_bytes = _encode_packet(_VALID_MESSAGE, declared_length=len(_VALID_MESSAGE) - 4)
    _assert_reason(parse_roughtime_v19_packet, packet_bytes, RoughtimeV19KernelReason.PACKET_MESSAGE_LENGTH_MISMATCH)


def test_packet_declared_length_too_large_rejected() -> None:
    packet_bytes = _encode_packet(_VALID_MESSAGE, declared_length=len(_VALID_MESSAGE) + 4)
    _assert_reason(parse_roughtime_v19_packet, packet_bytes, RoughtimeV19KernelReason.PACKET_MESSAGE_LENGTH_MISMATCH)


def test_packet_trailing_bytes_rejected() -> None:
    packet_bytes = _encode_packet(_VALID_MESSAGE, declared_length=len(_VALID_MESSAGE)) + b"\x00\x00\x00\x00"
    _assert_reason(parse_roughtime_v19_packet, packet_bytes, RoughtimeV19KernelReason.PACKET_MESSAGE_LENGTH_MISMATCH)


def test_packet_above_limit_rejected() -> None:
    _assert_reason(
        parse_roughtime_v19_packet,
        b"\x00" * (_EXPECTED_MAX_PACKET_BYTES + 1),
        RoughtimeV19KernelReason.PACKET_TOO_LARGE,
    )


# --- Negative: message framing ---------------------------------------------------------------------------
def test_message_fewer_than_four_bytes_rejected() -> None:
    _assert_reason(parse_roughtime_v19_message, b"\x00\x00\x00", RoughtimeV19KernelReason.MESSAGE_TOO_SHORT)


def test_message_pair_count_zero_rejected() -> None:
    _assert_reason(parse_roughtime_v19_message, _u32(0), RoughtimeV19KernelReason.PAIR_COUNT_ZERO)


def test_message_pair_count_above_limit_rejected() -> None:
    _assert_reason(
        parse_roughtime_v19_message,
        _u32(_EXPECTED_MAX_PAIR_COUNT + 1),
        RoughtimeV19KernelReason.PAIR_COUNT_EXCEEDS_LIMIT,
    )


def test_message_truncated_header_rejected() -> None:
    # N=2 needs an 16-byte header (count + 1 offset + 2 tags); supply only 12 bytes.
    truncated = _u32(2) + _u32(0) + _TAG_A
    _assert_reason(parse_roughtime_v19_message, truncated, RoughtimeV19KernelReason.HEADER_TRUNCATED)


def test_message_missing_offset_rejected() -> None:
    # N=2 but no offset word supplied (count + 2 tags = 12 bytes < 16-byte header).
    missing_offset = _u32(2) + _TAG_A + _TAG_B
    _assert_reason(parse_roughtime_v19_message, missing_offset, RoughtimeV19KernelReason.HEADER_TRUNCATED)


def test_message_missing_tag_rejected() -> None:
    # N=2 with the offset present but only one tag (count + 1 offset + 1 tag = 12 bytes < 16-byte header).
    missing_tag = _u32(2) + _u32(0) + _TAG_A
    _assert_reason(parse_roughtime_v19_message, missing_tag, RoughtimeV19KernelReason.HEADER_TRUNCATED)


def test_message_above_limit_rejected() -> None:
    _assert_reason(
        parse_roughtime_v19_message,
        b"\x00" * (_EXPECTED_MAX_MESSAGE_BYTES + 1),
        RoughtimeV19KernelReason.MESSAGE_TOO_LARGE,
    )


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
    # Byte-lexicographically ascending (AB.. < BA..) but little-endian numerically descending.
    raw = _encode_message_raw(2, [0], [_TAG_AB_LE, _TAG_BA_LE], b"")
    _assert_reason(parse_roughtime_v19_message, raw, RoughtimeV19KernelReason.TAG_ORDER_INVALID)


# --- Boundary coverage -----------------------------------------------------------------------------------
def test_packet_size_boundary() -> None:
    # Largest accepted packet: a max-size message inside a max-size packet.
    message_bytes = _u32(1) + _TAG_A + b"\x00" * (_EXPECTED_MAX_MESSAGE_BYTES - 8)
    assert len(message_bytes) == _EXPECTED_MAX_MESSAGE_BYTES
    packet_bytes = _encode_packet(message_bytes)
    assert len(packet_bytes) == _EXPECTED_MAX_PACKET_BYTES
    accepted = parse_roughtime_v19_packet(packet_bytes)
    assert accepted.message.pair_count == 1
    # First rejected size is exactly one byte larger.
    _assert_reason(parse_roughtime_v19_packet, packet_bytes + b"\x00", RoughtimeV19KernelReason.PACKET_TOO_LARGE)


def test_message_size_boundary() -> None:
    accepted_bytes = _u32(1) + _TAG_A + b"\x00" * (_EXPECTED_MAX_MESSAGE_BYTES - 8)
    assert len(accepted_bytes) == _EXPECTED_MAX_MESSAGE_BYTES
    accepted = parse_roughtime_v19_message(accepted_bytes)
    assert accepted.pair_count == 1
    assert len(accepted.fields[0].value) == _EXPECTED_MAX_MESSAGE_BYTES - 8
    _assert_reason(parse_roughtime_v19_message, accepted_bytes + b"\x00", RoughtimeV19KernelReason.MESSAGE_TOO_LARGE)


def test_pair_count_boundary() -> None:
    tags = _ascending_valid_tags(_EXPECTED_MAX_PAIR_COUNT)
    assert len(tags) == _EXPECTED_MAX_PAIR_COUNT
    accepted_bytes = _encode_canonical_message([(tag, b"") for tag in tags])
    accepted = parse_roughtime_v19_message(accepted_bytes)
    assert accepted.pair_count == _EXPECTED_MAX_PAIR_COUNT
    # First rejected pair count is exactly one larger (rejected before any header arithmetic).
    _assert_reason(
        parse_roughtime_v19_message,
        _u32(_EXPECTED_MAX_PAIR_COUNT + 1),
        RoughtimeV19KernelReason.PAIR_COUNT_EXCEEDS_LIMIT,
    )


# --- Contract pinning ------------------------------------------------------------------------------------
def test_defensive_limits_are_pinned() -> None:
    assert kernel_module._MAX_PACKET_BYTES == _EXPECTED_MAX_PACKET_BYTES
    assert kernel_module._MAX_MESSAGE_BYTES == _EXPECTED_MAX_MESSAGE_BYTES
    assert kernel_module._MAX_PAIR_COUNT == _EXPECTED_MAX_PAIR_COUNT
    # The message ceiling is exactly the packet ceiling minus the 12-byte outer frame.
    assert kernel_module._MAX_MESSAGE_BYTES == _EXPECTED_MAX_PACKET_BYTES - 12


def test_reason_inventory_is_closed_and_exact() -> None:
    expected = {
        "WRONG_INPUT_TYPE",
        "PACKET_TOO_SHORT",
        "PACKET_TOO_LARGE",
        "PACKET_MAGIC_MISMATCH",
        "PACKET_MESSAGE_LENGTH_MISMATCH",
        "MESSAGE_TOO_SHORT",
        "MESSAGE_TOO_LARGE",
        "PAIR_COUNT_ZERO",
        "PAIR_COUNT_EXCEEDS_LIMIT",
        "HEADER_TRUNCATED",
        "OFFSET_UNALIGNED",
        "OFFSET_ORDER_INVALID",
        "OFFSET_OUT_OF_BOUNDS",
        "TAG_INVALID",
        "TAG_ORDER_INVALID",
        "TAG_DUPLICATE",
    }
    assert {member.name for member in RoughtimeV19KernelReason} == expected
    values = [member.value for member in RoughtimeV19KernelReason]
    assert len(values) == len(set(values))
    assert all(value == value.lower() for value in values)


def test_public_api_names_exact() -> None:
    expected = {
        "RoughtimeV19KernelError",
        "RoughtimeV19KernelReason",
        "RoughtimeV19Field",
        "RoughtimeV19Message",
        "RoughtimeV19Packet",
        "parse_roughtime_v19_message",
        "parse_roughtime_v19_packet",
    }
    assert set(kernel_module.__all__) == expected
    for name in expected:
        assert hasattr(kernel_module, name)


def test_error_carries_closed_reason() -> None:
    error = RoughtimeV19KernelError(RoughtimeV19KernelReason.TAG_INVALID)
    assert error.reason is RoughtimeV19KernelReason.TAG_INVALID
    assert str(error) == "tag_invalid"


def test_field_is_frozen() -> None:
    field = RoughtimeV19Field(tag=_TAG_A, tag_uint32=_le(_TAG_A), value=b"")
    with pytest.raises(FrozenInstanceError):
        field.value = b"\x00"  # type: ignore[misc]


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
