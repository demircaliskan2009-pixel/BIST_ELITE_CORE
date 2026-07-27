"""Deterministic contract tests for the Roughtime draft-19 bounded REQUEST-INCLUSION Merkle verifier (K4).

Two independent oracle forms prove every positive expectation, so the code under test never proves itself:

1. LITERAL PINNED VECTORS — a complete 76-byte request packet, its full SHA-512, its 32-byte leaf, the
   incorrect message-only leaf, and three pinned roots (INDX 1, INDX 2, depth 32) are hard-coded below and were
   recomputed independently before being pinned.
2. A TEST-ONLY TREE ORACLE (``_oracle_root``) that takes explicit ``LEFT``/``RIGHT`` direction tokens, never
   reads ``INDX``, never imports K4 or any K4 constant or helper, and writes its own literal ``b"\\x00"`` and
   ``b"\\x01"`` prefixes. The ``INDX`` matching a direction sequence is derived separately by ``_oracle_index``.

Test-only packet encoders (``_encode_message`` / ``_encode_packet``) are independent of the production
decoders and never call any K4 function to produce an expected value. They follow the established K2/K3 test
encoding shape but are defined entirely inside this file.

Alignment note (K1 contract, inherited): every message value except the last in canonical tag order must be
four-byte aligned, so all fixture values here are four-aligned.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from crypto_core.validation.roughtime_v19_kernel import RoughtimeV19Field
from crypto_core.validation.roughtime_v19_request_inclusion import (
    ROUGHTIME_V19_REQUEST_INCLUSION_PROFILE_ID,
    RoughtimeV19RequestInclusion,
    RoughtimeV19RequestInclusionError,
    RoughtimeV19RequestInclusionReason,
    verify_roughtime_v19_request_inclusion,
)
from crypto_core.validation.roughtime_v19_request_semantics import (
    RoughtimeV19RequestSemantics,
    parse_roughtime_v19_request,
)
from crypto_core.validation.roughtime_v19_response_semantics import (
    RoughtimeV19CertificateSemantics,
    RoughtimeV19DelegationSemantics,
    RoughtimeV19ResponseSemantics,
    RoughtimeV19SignedResponseSemantics,
    parse_roughtime_v19_response,
)

R = RoughtimeV19RequestInclusionReason

# --- Independently pinned identity constants --------------------------------------------------------------
_EXPECTED_PROFILE_ID = "roughtime-v19-request-inclusion-bounded-k4.v1"
_EXPECTED_SEAL_MESSAGE = "RoughtimeV19RequestInclusion is a sealed artifact type and cannot be subclassed"
_EXPECTED_REASON_TYPE_MESSAGE = "RoughtimeV19RequestInclusionError requires a RoughtimeV19RequestInclusionReason member"
_EXPECTED_REASON_VALUES = (
    "wrong_input_type",
    "input_artifact_inconsistent",
    "index_unused_bits_set",
    "root_mismatch",
    "artifact_inclusion_inconsistent",
)
_EXPECTED_ARTIFACT_FIELDS = (
    "request_raw",
    "response_raw",
    "leaf",
    "computed_root",
    "declared_root",
    "path_length",
    "index",
)
_FORBIDDEN_FIELD_TOKENS = (
    "proven",
    "valid",
    "verified",
    "authentic",
    "ready",
    "admitted",
    "accepted",
    "provider",
    "time",
    "key",
)

# --- Independently pinned fixed vectors (recomputed before pinning; never produced by K4) -----------------
_FIXED_REQUEST_HEX = (
    "524f55474854494d40000000030000000400000024000000564552004e4f4e43545950450100000000010203040506070809"
    "0a0b0c0d0e0f101112131415161718191a1b1c1d1e1f00000000"
)
_FIXED_REQUEST = bytes.fromhex(_FIXED_REQUEST_HEX)
_FIXED_REQUEST_LENGTH = 76
_FIXED_FULL_SHA512_HEX = (
    "5b63620a6c188a004267027b4f16067bee3044f4cd1626328750e5081829a959"
    "dbd2ec9e5c2a86176e2755c74509aada4ecd527963b8c2f99483668415437a0c"
)
_FIXED_LEAF_HEX = "5b63620a6c188a004267027b4f16067bee3044f4cd1626328750e5081829a959"
_FIXED_MESSAGE_ONLY_LEAF_HEX = "9bd3c0da4d5fc737e4fd8634ccde5ee2bcc83efe5d54a91a06e95cf1dbbd7bc1"
_FIXED_PATH_0 = bytes.fromhex("a0a1a2a3a4a5a6a7a8a9aaabacadaeafb0b1b2b3b4b5b6b7b8b9babbbcbdbebf")
_FIXED_PATH_1 = bytes.fromhex("c0c1c2c3c4c5c6c7c8c9cacbcccdcecfd0d1d2d3d4d5d6d7d8d9dadbdcdddedf")
_FIXED_ROOT_INDEX_1_HEX = "94574df8060c5916b3a3f19c83607dbf46bb9fa07343731521059f654e09341e"
_FIXED_ROOT_INDEX_2_HEX = "6148eb54bab619a6fccb89343079a9810e845c74322115c88160afa1f7f22639"
_FIXED_ROOT_DEPTH_32_HEX = "51deaac87e587e40f784ff55304559b7e877f55d61c6bfe2e64e79699bbe2660"

_MAGIC = b"ROUGHTIM"
_DIGEST_BYTES = 32

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
_TAG_SRV = b"SRV\x00"
_TAG_ZZZZ = b"ZZZZ"
_TAG_UNKNOWN = b"YY\x00\x00"

_REQUEST_NONCE = bytes(range(32))
_RESPONSE_NONCE = bytes(range(32))
_OTHER_NONCE = bytes(range(100, 132))


# --- Test-only encoders (independent of production) -------------------------------------------------------
def _le(tag: bytes) -> int:
    return int.from_bytes(tag, "little")


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "little")


def _u64(value: int) -> bytes:
    return int(value).to_bytes(8, "little")


def _encode_message(pairs: list[tuple[bytes, bytes]]) -> bytes:
    """Encode a generic K1 message from (tag, value) pairs, sorting tags by little-endian uint32."""
    ordered = sorted(pairs, key=lambda pair: _le(pair[0]))
    tags = [tag for tag, _ in ordered]
    values = [value for _, value in ordered]
    count = len(ordered)
    out = _u32(count)
    cumulative = 0
    for index in range(count - 1):
        cumulative += len(values[index])
        out += _u32(cumulative)
    for tag in tags:
        out += tag
    for value in values:
        out += value
    return out


def _encode_packet(message_bytes: bytes) -> bytes:
    return _MAGIC + _u32(len(message_bytes)) + message_bytes


# --- Test-only tree oracle (explicit direction tokens; never reads INDX; never imports K4) ----------------
LEFT = "LEFT"
RIGHT = "RIGHT"


def _oracle_leaf(request_packet: bytes) -> bytes:
    return hashlib.sha512(b"\x00" + request_packet).digest()[:32]


def _oracle_root(leaf: bytes, steps: tuple[tuple[str, bytes], ...]) -> bytes:
    """Fold with explicit direction tokens naming where the ACCUMULATOR sits at each depth."""
    current = leaf
    for direction, sibling in steps:
        if direction == LEFT:
            current = hashlib.sha512(b"\x01" + current + sibling).digest()[:32]
        elif direction == RIGHT:
            current = hashlib.sha512(b"\x01" + sibling + current).digest()[:32]
        else:
            raise ValueError("direction must be LEFT or RIGHT")
    return current


def _oracle_index(directions: tuple[str, ...]) -> int:
    """Separately derive the INDX matching a direction sequence: bit d is set iff the accumulator is RIGHT."""
    index = 0
    for depth, direction in enumerate(directions):
        if direction == RIGHT:
            index |= 1 << depth
    return index


# --- Test-only request builders ---------------------------------------------------------------------------
def _request_packet(*, nonce: bytes = _REQUEST_NONCE, versions=(1,), srv=None, zzzz=None, unknown=None) -> bytes:
    pairs: list[tuple[bytes, bytes]] = [
        (_TAG_VER, b"".join(_u32(version) for version in versions)),
        (_TAG_NONC, nonce),
        (_TAG_TYPE, _u32(0)),
    ]
    if srv is not None:
        pairs.append((_TAG_SRV, srv))
    if unknown is not None:
        pairs.append((_TAG_UNKNOWN, unknown))
    if zzzz is not None:
        pairs.append((_TAG_ZZZZ, zzzz))
    return _encode_packet(_encode_message(pairs))


# --- Test-only response builders --------------------------------------------------------------------------
_OUTER_SIG64 = bytes(range(64))
_CERT_SIG64 = bytes(range(100, 164))
_PUBK32 = bytes(range(200, 232))


def _dele_raw() -> bytes:
    return _encode_message([(_TAG_PUBK, _PUBK32), (_TAG_MINT, _u64(100)), (_TAG_MAXT, _u64(200))])


def _cert_raw() -> bytes:
    return _encode_message([(_TAG_SIG, _CERT_SIG64), (_TAG_DELE, _dele_raw())])


def _srep_raw(root: bytes, *, selected_version: int = 1, versions=(1, 0x40000001)) -> bytes:
    return _encode_message(
        [
            (_TAG_VER, _u32(selected_version)),
            (_TAG_RADI, _u32(3)),
            (_TAG_MIDP, _u64(150)),
            (_TAG_VERS, b"".join(_u32(version) for version in versions)),
            (_TAG_ROOT, root),
        ]
    )


def _response_packet(
    *,
    root: bytes,
    path: tuple[bytes, ...] = (),
    index: int = 0,
    nonce: bytes = _RESPONSE_NONCE,
    selected_version: int = 1,
    versions=(1, 0x40000001),
) -> bytes:
    pairs: list[tuple[bytes, bytes]] = [
        (_TAG_SIG, _OUTER_SIG64),
        (_TAG_NONC, nonce),
        (_TAG_TYPE, _u32(1)),
        (_TAG_PATH, b"".join(path)),
        (_TAG_SREP, _srep_raw(root, selected_version=selected_version, versions=versions)),
        (_TAG_CERT, _cert_raw()),
        (_TAG_INDX, _u32(index)),
    ]
    return _encode_packet(_encode_message(pairs))


def _pair(
    *,
    request_packet: bytes | None = None,
    path: tuple[bytes, ...] = (),
    directions: tuple[str, ...] | None = None,
    index: int | None = None,
    root: bytes | None = None,
    response_nonce: bytes = _RESPONSE_NONCE,
    selected_version: int = 1,
    versions=(1, 0x40000001),
) -> tuple[RoughtimeV19RequestSemantics, RoughtimeV19ResponseSemantics]:
    """Build a matching (request, response) pair using ONLY the oracle to derive the root and index."""
    packet = _request_packet() if request_packet is None else request_packet
    if directions is None:
        directions = tuple(LEFT for _ in path)
    steps = tuple(zip(directions, path))
    derived_index = _oracle_index(directions) if index is None else index
    derived_root = _oracle_root(_oracle_leaf(packet), steps) if root is None else root
    response_bytes = _response_packet(
        root=derived_root,
        path=path,
        index=derived_index,
        nonce=response_nonce,
        selected_version=selected_version,
        versions=versions,
    )
    return parse_roughtime_v19_request(packet), parse_roughtime_v19_response(response_bytes)


def _hollow(cls, **fields):
    """Build an EXACT-type instance without running its initializer, mirroring the real bypass K2 allows."""
    obj = object.__new__(cls)
    for name, value in fields.items():
        object.__setattr__(obj, name, value)
    return obj


def _response_state(response: RoughtimeV19ResponseSemantics) -> dict:
    return {
        "signature": response.signature,
        "nonce": response.nonce,
        "message_type": response.message_type,
        "path": response.path,
        "index": response.index,
        "signed_response": response.signed_response,
        "certificate": response.certificate,
        "extensions": response.extensions,
        "raw": response.raw,
    }


def _request_state(request: RoughtimeV19RequestSemantics) -> dict:
    return {
        "versions": request.versions,
        "nonce": request.nonce,
        "message_type": request.message_type,
        "server_key_id": request.server_key_id,
        "padding": request.padding,
        "extensions": request.extensions,
        "raw": request.raw,
    }


_PRODUCTION_PATH = (
    Path(__file__).resolve().parents[3] / "src" / "crypto_core" / "validation" / "roughtime_v19_request_inclusion.py"
)


# ============================================================================================================
# Fixed-vector correctness
# ============================================================================================================
def test_fixed_request_vector_length_is_exactly_76() -> None:
    assert len(_FIXED_REQUEST) == _FIXED_REQUEST_LENGTH


def test_fixed_request_vector_matches_independent_encoder() -> None:
    assert _request_packet() == _FIXED_REQUEST


def test_fixed_full_sha512_is_exact() -> None:
    assert hashlib.sha512(b"\x00" + _FIXED_REQUEST).hexdigest() == _FIXED_FULL_SHA512_HEX


def test_fixed_leaf_is_first_32_bytes_of_full_sha512() -> None:
    assert _FIXED_LEAF_HEX == _FIXED_FULL_SHA512_HEX[: _DIGEST_BYTES * 2]
    assert _FIXED_LEAF_HEX != _FIXED_FULL_SHA512_HEX[-_DIGEST_BYTES * 2 :]
    assert _oracle_leaf(_FIXED_REQUEST).hex() == _FIXED_LEAF_HEX


def test_every_digest_field_is_exactly_32_bytes() -> None:
    request, response = _pair(path=(_FIXED_PATH_0,), directions=(RIGHT,))
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert len(artifact.leaf) == _DIGEST_BYTES
    assert len(artifact.computed_root) == _DIGEST_BYTES
    assert len(artifact.declared_root) == _DIGEST_BYTES


def test_message_only_leaf_differs_and_matches_its_pinned_incorrect_value() -> None:
    message_only = hashlib.sha512(b"\x00" + _FIXED_REQUEST[12:]).digest()[:32]
    assert message_only.hex() == _FIXED_MESSAGE_ONLY_LEAF_HEX
    assert message_only.hex() != _FIXED_LEAF_HEX


def test_verifier_leaf_uses_complete_packet_not_message() -> None:
    request, response = _pair()
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert artifact.leaf.hex() == _FIXED_LEAF_HEX
    assert artifact.leaf.hex() != _FIXED_MESSAGE_ONLY_LEAF_HEX


def test_fixed_root_index_1_is_exact() -> None:
    request, response = _pair(path=(_FIXED_PATH_0, _FIXED_PATH_1), directions=(RIGHT, LEFT))
    assert response.index == 1
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert artifact.computed_root.hex() == _FIXED_ROOT_INDEX_1_HEX


def test_fixed_root_index_2_is_exact() -> None:
    request, response = _pair(path=(_FIXED_PATH_0, _FIXED_PATH_1), directions=(LEFT, RIGHT))
    assert response.index == 2
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert artifact.computed_root.hex() == _FIXED_ROOT_INDEX_2_HEX


def test_fixed_root_depth_32_is_exact() -> None:
    path = tuple(bytes([depth]) * 32 for depth in range(32))
    request, response = _pair(path=path, directions=tuple(RIGHT for _ in range(32)))
    assert response.index == 0xFFFFFFFF
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert artifact.computed_root.hex() == _FIXED_ROOT_DEPTH_32_HEX
    assert artifact.path_length == 32


# ============================================================================================================
# Positive inclusion
# ============================================================================================================
def test_empty_path_root_equals_leaf() -> None:
    request, response = _pair()
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert artifact.path_length == 0
    assert artifact.index == 0
    assert artifact.computed_root == artifact.leaf
    assert artifact.computed_root == artifact.declared_root


def test_single_node_bit_zero_accumulator_is_left() -> None:
    request, response = _pair(path=(_FIXED_PATH_0,), directions=(LEFT,))
    assert response.index == 0
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    expected = hashlib.sha512(b"\x01" + _oracle_leaf(_FIXED_REQUEST) + _FIXED_PATH_0).digest()[:32]
    assert artifact.computed_root == expected


def test_single_node_bit_one_sibling_is_left() -> None:
    request, response = _pair(path=(_FIXED_PATH_0,), directions=(RIGHT,))
    assert response.index == 1
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    expected = hashlib.sha512(b"\x01" + _FIXED_PATH_0 + _oracle_leaf(_FIXED_REQUEST)).digest()[:32]
    assert artifact.computed_root == expected


@pytest.mark.parametrize(
    "directions",
    [
        (LEFT, LEFT, LEFT),
        (RIGHT, LEFT, RIGHT),
        (LEFT, RIGHT, RIGHT),
    ],
)
def test_three_node_paths_verify(directions) -> None:
    path = (_FIXED_PATH_0, _FIXED_PATH_1, bytes(range(32)))
    request, response = _pair(path=path, directions=directions)
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert artifact.path_length == 3
    assert artifact.computed_root == _oracle_root(_oracle_leaf(_FIXED_REQUEST), tuple(zip(directions, path)))


def test_seven_node_path_verifies() -> None:
    path = tuple(bytes([0xE0 + depth]) * 32 for depth in range(7))
    directions = (RIGHT, LEFT, RIGHT, RIGHT, LEFT, LEFT, RIGHT)
    request, response = _pair(path=path, directions=directions)
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert artifact.path_length == 7
    assert artifact.index == _oracle_index(directions)
    assert artifact.computed_root == _oracle_root(_oracle_leaf(_FIXED_REQUEST), tuple(zip(directions, path)))


def test_request_with_optional_srv_verifies() -> None:
    packet = _request_packet(srv=bytes(range(60, 92)))
    request, response = _pair(request_packet=packet, path=(_FIXED_PATH_0,), directions=(RIGHT,))
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert request.server_key_id == bytes(range(60, 92))
    assert artifact.leaf == _oracle_leaf(packet)
    assert artifact.leaf != _oracle_leaf(_FIXED_REQUEST)


def test_request_with_present_zzzz_padding_verifies() -> None:
    packet = _request_packet(zzzz=b"\x00\x00\x00\x00")
    request, response = _pair(request_packet=packet)
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert request.padding == b"\x00\x00\x00\x00"
    assert artifact.leaf == _oracle_leaf(packet)


def test_request_with_unknown_extension_verifies() -> None:
    packet = _request_packet(unknown=b"\xde\xad\xbe\xef")
    request, response = _pair(request_packet=packet, path=(_FIXED_PATH_1,), directions=(LEFT,))
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert len(request.extensions) == 1
    assert artifact.leaf == _oracle_leaf(packet)


def test_minimal_valid_request_verifies() -> None:
    packet = _request_packet(versions=(1,))
    request, response = _pair(request_packet=packet)
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert artifact.request_raw == packet


def test_repeated_verification_is_deterministic_and_hashable() -> None:
    request, response = _pair(path=(_FIXED_PATH_0, _FIXED_PATH_1), directions=(RIGHT, LEFT))
    first = verify_roughtime_v19_request_inclusion(request, response)
    second = verify_roughtime_v19_request_inclusion(request, response)
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1


def test_artifact_carries_exact_canonical_bytes() -> None:
    request, response = _pair(path=(_FIXED_PATH_0,), directions=(LEFT,))
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert artifact.request_raw == request.raw
    assert artifact.response_raw == response.raw
    assert artifact.declared_root == response.signed_response.root
    assert artifact.index == response.index
    assert artifact.path_length == len(response.path)


# ============================================================================================================
# Unused-index-bit behavior
# ============================================================================================================
def test_empty_path_with_nonzero_index_rejected() -> None:
    request, response = _pair(index=1)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, response)
    assert excinfo.value.reason is R.INDEX_UNUSED_BITS_SET


def test_one_unused_bit_exactly_at_path_length_rejected() -> None:
    path = (_FIXED_PATH_0, _FIXED_PATH_1)
    directions = (RIGHT, LEFT)
    root = _oracle_root(_oracle_leaf(_FIXED_REQUEST), tuple(zip(directions, path)))
    request, response = _pair(path=path, directions=directions, index=1 | (1 << 2), root=root)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, response)
    assert excinfo.value.reason is R.INDEX_UNUSED_BITS_SET


def test_multiple_unused_high_bits_rejected() -> None:
    request, response = _pair(path=(_FIXED_PATH_0,), directions=(LEFT,), index=0xFFFFFFF0)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, response)
    assert excinfo.value.reason is R.INDEX_UNUSED_BITS_SET


def test_unused_index_bits_precede_root_mismatch() -> None:
    """The consumed bits give the pinned correct root, yet an unused high bit still rejects first."""
    path = (_FIXED_PATH_0, _FIXED_PATH_1)
    correct_root = bytes.fromhex(_FIXED_ROOT_INDEX_1_HEX)
    request, response = _pair(path=path, index=1 | (1 << 5), root=correct_root)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, response)
    assert excinfo.value.reason is R.INDEX_UNUSED_BITS_SET


def test_depth_32_index_has_no_unused_bits() -> None:
    path = tuple(bytes([depth]) * 32 for depth in range(32))
    request, response = _pair(path=path, directions=tuple(RIGHT for _ in range(32)))
    assert response.index >> len(response.path) == 0
    verify_roughtime_v19_request_inclusion(request, response)


# ============================================================================================================
# Root mismatch
# ============================================================================================================
def test_declared_root_last_byte_flip_rejected() -> None:
    correct = bytes.fromhex(_FIXED_ROOT_INDEX_1_HEX)
    tampered = correct[:-1] + bytes([correct[-1] ^ 0x01])
    request, response = _pair(path=(_FIXED_PATH_0, _FIXED_PATH_1), index=1, root=tampered)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, response)
    assert excinfo.value.reason is R.ROOT_MISMATCH


def test_path_node_one_bit_flip_rejected() -> None:
    flipped = bytes([_FIXED_PATH_0[0] ^ 0x01]) + _FIXED_PATH_0[1:]
    request, response = _pair(path=(flipped, _FIXED_PATH_1), index=1, root=bytes.fromhex(_FIXED_ROOT_INDEX_1_HEX))
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, response)
    assert excinfo.value.reason is R.ROOT_MISMATCH


def test_swapped_adjacent_path_nodes_rejected() -> None:
    request, response = _pair(path=(_FIXED_PATH_1, _FIXED_PATH_0), index=1, root=bytes.fromhex(_FIXED_ROOT_INDEX_1_HEX))
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, response)
    assert excinfo.value.reason is R.ROOT_MISMATCH


def test_inverted_used_index_bit_rejected() -> None:
    """Index 2 consumes both bits with no unused bit set, but inverts the child order versus index 1."""
    request, response = _pair(path=(_FIXED_PATH_0, _FIXED_PATH_1), index=2, root=bytes.fromhex(_FIXED_ROOT_INDEX_1_HEX))
    assert response.index >> len(response.path) == 0
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, response)
    assert excinfo.value.reason is R.ROOT_MISMATCH


def test_request_packet_semantic_valid_mutation_rejected() -> None:
    """A different but fully valid nonce changes the leaf, so the pinned root no longer holds."""
    mutated = _request_packet(nonce=_OTHER_NONCE)
    request, response = _pair(
        request_packet=mutated,
        path=(_FIXED_PATH_0, _FIXED_PATH_1),
        index=1,
        root=bytes.fromhex(_FIXED_ROOT_INDEX_1_HEX),
    )
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, response)
    assert excinfo.value.reason is R.ROOT_MISMATCH


# ============================================================================================================
# Domain separation and truncation
# ============================================================================================================
def _wrong_root_leaf_prefix_one() -> bytes:
    leaf = hashlib.sha512(b"\x01" + _FIXED_REQUEST).digest()[:32]
    return _oracle_root(leaf, ((RIGHT, _FIXED_PATH_0), (LEFT, _FIXED_PATH_1)))


def _wrong_root_internal_prefix_zero() -> bytes:
    current = _oracle_leaf(_FIXED_REQUEST)
    current = hashlib.sha512(b"\x00" + _FIXED_PATH_0 + current).digest()[:32]
    return hashlib.sha512(b"\x00" + current + _FIXED_PATH_1).digest()[:32]


def _wrong_root_no_prefix_leaf() -> bytes:
    leaf = hashlib.sha512(_FIXED_REQUEST).digest()[:32]
    return _oracle_root(leaf, ((RIGHT, _FIXED_PATH_0), (LEFT, _FIXED_PATH_1)))


def _wrong_root_no_prefix_internal() -> bytes:
    current = _oracle_leaf(_FIXED_REQUEST)
    current = hashlib.sha512(_FIXED_PATH_0 + current).digest()[:32]
    return hashlib.sha512(current + _FIXED_PATH_1).digest()[:32]


def _wrong_root_last_32_truncation() -> bytes:
    leaf = hashlib.sha512(b"\x00" + _FIXED_REQUEST).digest()[-32:]
    current = hashlib.sha512(b"\x01" + _FIXED_PATH_0 + leaf).digest()[-32:]
    return hashlib.sha512(b"\x01" + current + _FIXED_PATH_1).digest()[-32:]


def _wrong_root_msb_first() -> bytes:
    """Index 1 over two nodes: MSB-first yields LEFT then RIGHT, the reverse of the normative LSB-first."""
    return _oracle_root(_oracle_leaf(_FIXED_REQUEST), ((LEFT, _FIXED_PATH_0), (RIGHT, _FIXED_PATH_1)))


@pytest.mark.parametrize(
    "wrong_root_builder",
    [
        _wrong_root_leaf_prefix_one,
        _wrong_root_internal_prefix_zero,
        _wrong_root_no_prefix_leaf,
        _wrong_root_no_prefix_internal,
        _wrong_root_last_32_truncation,
        _wrong_root_msb_first,
    ],
)
def test_wrong_domain_separation_or_order_never_verifies(wrong_root_builder) -> None:
    wrong_root = wrong_root_builder()
    assert wrong_root != bytes.fromhex(_FIXED_ROOT_INDEX_1_HEX)
    request, response = _pair(path=(_FIXED_PATH_0, _FIXED_PATH_1), index=1, root=wrong_root)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, response)
    assert excinfo.value.reason is R.ROOT_MISMATCH


# ============================================================================================================
# Nonce deferral
# ============================================================================================================
def test_differing_outer_nonce_still_verifies() -> None:
    request, response = _pair(path=(_FIXED_PATH_0,), directions=(RIGHT,), response_nonce=_OTHER_NONCE)
    assert response.nonce != request.nonce
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert artifact.computed_root == artifact.declared_root


def test_artifact_exposes_no_nonce_field() -> None:
    fields = tuple(RoughtimeV19RequestInclusion.__dataclass_fields__)
    assert not any("nonce" in name for name in fields)


def test_reason_inventory_has_no_nonce_reason() -> None:
    assert not any("nonce" in member.value for member in RoughtimeV19RequestInclusionReason)


# ============================================================================================================
# Version deferral
# ============================================================================================================
def test_unoffered_selected_version_still_verifies() -> None:
    unoffered = 0x40000001
    request, response = _pair(
        path=(_FIXED_PATH_1,),
        directions=(LEFT,),
        selected_version=unoffered,
        versions=(1, unoffered),
    )
    assert response.signed_response.version == unoffered
    assert unoffered not in request.versions
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert artifact.computed_root == artifact.declared_root


def test_artifact_exposes_no_version_field() -> None:
    fields = tuple(RoughtimeV19RequestInclusion.__dataclass_fields__)
    assert not any("version" in name for name in fields)


def test_reason_inventory_has_no_version_reason() -> None:
    assert not any("version" in member.value for member in RoughtimeV19RequestInclusionReason)


# ============================================================================================================
# Input trust boundary
# ============================================================================================================
_HOSTILE_ACCESS: list[str] = []


def _define_hostile_response_subclass() -> type:
    class _HostileResponse(RoughtimeV19ResponseSemantics):
        def __getattribute__(self, name: str) -> object:
            _HOSTILE_ACCESS.append("__getattribute__:" + name)
            return object.__getattribute__(self, name)

    return _HostileResponse


def _define_unvalidated_response_subclass() -> type:
    class _UnvalidatedResponse(RoughtimeV19ResponseSemantics):
        def __post_init__(self) -> None:
            _HOSTILE_ACCESS.append("__post_init__")

    return _UnvalidatedResponse


def test_wrong_ordinary_object_rejected_as_wrong_input_type() -> None:
    request, response = _pair()
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(object(), response)
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, object())
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_swapped_argument_types_rejected() -> None:
    request, response = _pair()
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(response, request)
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_k2_subclass_with_value_correct_state_rejected_before_any_attribute_read() -> None:
    request, response = _pair(path=(_FIXED_PATH_0,), directions=(LEFT,))
    hostile_cls = _define_hostile_response_subclass()
    hostile = hostile_cls(**_response_state(response))
    _HOSTILE_ACCESS.clear()
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, hostile)
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE
    assert _HOSTILE_ACCESS == []


def test_k2_subclass_skipping_validation_rejected_before_any_attribute_read() -> None:
    request, response = _pair()
    unvalidated_cls = _define_unvalidated_response_subclass()
    forged = unvalidated_cls(
        signature=b"",
        nonce=b"",
        message_type=0,
        path=(),
        index=0,
        signed_response=None,
        certificate=None,
        extensions=(),
        raw=b"",
    )
    _HOSTILE_ACCESS.clear()
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, forged)
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE
    assert _HOSTILE_ACCESS == []


def test_k3_artifact_cannot_be_subclassed_at_all() -> None:
    with pytest.raises(TypeError):
        type("_ForgedRequest", (RoughtimeV19RequestSemantics,), {})


def test_hollow_exact_base_response_with_raw_only_rejected() -> None:
    request, response = _pair()
    hollow = _hollow(RoughtimeV19ResponseSemantics, raw=response.raw)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, hollow)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_hollow_exact_base_request_with_raw_only_rejected() -> None:
    request, response = _pair()
    hollow = _hollow(RoughtimeV19RequestSemantics, raw=request.raw)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(hollow, response)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


@pytest.mark.parametrize("dropped", ["signature", "path", "index", "signed_response", "certificate", "raw"])
def test_exact_base_response_missing_one_declared_field_rejected(dropped) -> None:
    request, response = _pair()
    state = _response_state(response)
    del state[dropped]
    hollow = _hollow(RoughtimeV19ResponseSemantics, **state)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, hollow)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_exact_base_response_with_mutated_consumed_field_rejected() -> None:
    """``index`` feeds the fold; a declared value diverging from raw must never be admitted."""
    request, response = _pair(path=(_FIXED_PATH_0,), directions=(LEFT,))
    state = _response_state(response)
    state["index"] = 1
    hollow = _hollow(RoughtimeV19ResponseSemantics, **state)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, hollow)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_exact_base_response_with_mutated_unused_field_rejected() -> None:
    """``signature`` is never read by the Merkle computation, so only full revalidation can catch this."""
    request, response = _pair()
    state = _response_state(response)
    state["signature"] = bytes(64)
    hollow = _hollow(RoughtimeV19ResponseSemantics, **state)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, hollow)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_exact_base_request_with_mutated_unused_field_rejected() -> None:
    request, response = _pair()
    state = _request_state(request)
    state["nonce"] = _OTHER_NONCE
    hollow = _hollow(RoughtimeV19RequestSemantics, **state)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(hollow, response)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_forged_nested_signed_response_rejected() -> None:
    request, response = _pair()
    state = _response_state(response)
    forged_root = bytes(32)
    state["signed_response"] = _hollow(
        RoughtimeV19SignedResponseSemantics,
        version=response.signed_response.version,
        radius_seconds=response.signed_response.radius_seconds,
        midpoint_seconds=response.signed_response.midpoint_seconds,
        versions=response.signed_response.versions,
        root=forged_root,
        extensions=response.signed_response.extensions,
        raw=response.signed_response.raw,
    )
    hollow = _hollow(RoughtimeV19ResponseSemantics, **state)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, hollow)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_forged_nested_certificate_rejected() -> None:
    request, response = _pair()
    state = _response_state(response)
    state["certificate"] = _hollow(
        RoughtimeV19CertificateSemantics,
        signature=bytes(64),
        delegation=response.certificate.delegation,
        extensions=response.certificate.extensions,
        raw=response.certificate.raw,
    )
    hollow = _hollow(RoughtimeV19ResponseSemantics, **state)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, hollow)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_forged_nested_delegation_rejected() -> None:
    request, response = _pair()
    delegation = response.certificate.delegation
    forged_delegation = _hollow(
        RoughtimeV19DelegationSemantics,
        pubk=bytes(32),
        min_time=delegation.min_time,
        max_time=delegation.max_time,
        extensions=delegation.extensions,
        raw=delegation.raw,
    )
    state = _response_state(response)
    state["certificate"] = _hollow(
        RoughtimeV19CertificateSemantics,
        signature=response.certificate.signature,
        delegation=forged_delegation,
        extensions=response.certificate.extensions,
        raw=response.certificate.raw,
    )
    hollow = _hollow(RoughtimeV19ResponseSemantics, **state)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, hollow)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


@pytest.mark.parametrize("bad_raw", [b"", b"NOTROUGH", b"ROUGHTIM\x04\x00\x00\x00", bytearray(b"ROUGHTIM")])
def test_exact_base_response_with_unparsable_raw_rejected(bad_raw) -> None:
    request, response = _pair()
    state = _response_state(response)
    state["raw"] = bad_raw
    hollow = _hollow(RoughtimeV19ResponseSemantics, **state)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        verify_roughtime_v19_request_inclusion(request, hollow)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_no_underlying_k2_or_k3_error_ever_leaks() -> None:
    request, response = _pair()
    hollow = _hollow(RoughtimeV19ResponseSemantics, raw=b"")
    with pytest.raises(RoughtimeV19RequestInclusionError):
        verify_roughtime_v19_request_inclusion(request, hollow)


# ============================================================================================================
# Direct artifact construction
# ============================================================================================================
def _valid_artifact_fields() -> dict:
    path = (_FIXED_PATH_0, _FIXED_PATH_1)
    directions = (RIGHT, LEFT)
    leaf = _oracle_leaf(_FIXED_REQUEST)
    root = _oracle_root(leaf, tuple(zip(directions, path)))
    response_bytes = _response_packet(root=root, path=path, index=_oracle_index(directions))
    return {
        "request_raw": _FIXED_REQUEST,
        "response_raw": response_bytes,
        "leaf": leaf,
        "computed_root": root,
        "declared_root": root,
        "path_length": 2,
        "index": 1,
    }


def test_direct_construction_from_independent_values_succeeds() -> None:
    artifact = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    assert artifact.computed_root.hex() == _FIXED_ROOT_INDEX_1_HEX


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("leaf", bytes(32)),
        ("computed_root", bytes(32)),
        ("declared_root", bytes(32)),
        ("path_length", 1),
        ("path_length", 3),
        ("index", 0),
        ("index", 2),
        ("request_raw", _request_packet(nonce=_OTHER_NONCE)),
    ],
)
def test_direct_construction_field_mismatch_rejected(field, value) -> None:
    fields = _valid_artifact_fields()
    fields[field] = value
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion(**fields)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_direct_construction_substituted_response_raw_rejected() -> None:
    fields = _valid_artifact_fields()
    fields["response_raw"] = _response_packet(root=bytes(32))
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion(**fields)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_raw", bytearray(_FIXED_REQUEST)),
        ("response_raw", None),
        ("leaf", None),
        ("computed_root", "not-bytes"),
        ("declared_root", 0),
        ("path_length", "2"),
        ("index", None),
    ],
)
def test_direct_construction_wrong_exact_type_rejected(field, value) -> None:
    fields = _valid_artifact_fields()
    fields[field] = value
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion(**fields)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_direct_construction_bytes_subclass_rejected() -> None:
    class _Bytes(bytes):
        pass

    fields = _valid_artifact_fields()
    fields["leaf"] = _Bytes(fields["leaf"])
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion(**fields)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_direct_construction_int_subclass_rejected() -> None:
    class _Int(int):
        pass

    fields = _valid_artifact_fields()
    fields["index"] = _Int(1)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion(**fields)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_direct_construction_bool_for_integer_field_rejected() -> None:
    path = (_FIXED_PATH_0,)
    directions = (RIGHT,)
    leaf = _oracle_leaf(_FIXED_REQUEST)
    root = _oracle_root(leaf, tuple(zip(directions, path)))
    fields = {
        "request_raw": _FIXED_REQUEST,
        "response_raw": _response_packet(root=root, path=path, index=1),
        "leaf": leaf,
        "computed_root": root,
        "declared_root": root,
        "path_length": 1,
        "index": True,
    }
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion(**fields)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


@pytest.mark.parametrize("short", [b"", bytes(31), bytes(33), bytes(64)])
def test_direct_construction_wrong_digest_length_rejected(short) -> None:
    fields = _valid_artifact_fields()
    fields["leaf"] = short
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion(**fields)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_direct_construction_with_unused_index_bits_rejected() -> None:
    path = (_FIXED_PATH_0,)
    leaf = _oracle_leaf(_FIXED_REQUEST)
    root = _oracle_root(leaf, ((RIGHT, _FIXED_PATH_0),))
    fields = {
        "request_raw": _FIXED_REQUEST,
        "response_raw": _response_packet(root=root, path=path, index=0b11),
        "leaf": leaf,
        "computed_root": root,
        "declared_root": root,
        "path_length": 1,
        "index": 0b11,
    }
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion(**fields)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_direct_construction_with_root_mismatch_encoded_in_raw_rejected() -> None:
    path = (_FIXED_PATH_0,)
    leaf = _oracle_leaf(_FIXED_REQUEST)
    wrong_root = bytes(range(32))
    fields = {
        "request_raw": _FIXED_REQUEST,
        "response_raw": _response_packet(root=wrong_root, path=path, index=1),
        "leaf": leaf,
        "computed_root": wrong_root,
        "declared_root": wrong_root,
        "path_length": 1,
        "index": 1,
    }
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion(**fields)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


@pytest.mark.parametrize("bad_raw", [b"", b"ROUGHTIM", b"\x00" * 12])
def test_direct_construction_with_unparsable_raw_rejected(bad_raw) -> None:
    fields = _valid_artifact_fields()
    fields["request_raw"] = bad_raw
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion(**fields)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT
    fields = _valid_artifact_fields()
    fields["response_raw"] = bad_raw
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion(**fields)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_hollow_artifact_rejected_by_exact_type_gate_via_unbound_post_init() -> None:
    foreign = _hollow(RoughtimeV19ResponseSemantics, raw=b"")
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion.__post_init__(foreign)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_artifact_is_frozen() -> None:
    artifact = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    with pytest.raises(FrozenInstanceError):
        artifact.index = 5
    with pytest.raises(FrozenInstanceError):
        del artifact.index


# ============================================================================================================
# Exact instance-namespace boundary (Sol Ultra Stage-2 P2-1)
#
# A frozen dataclass compares and hashes ONLY its declared fields, so an artifact carrying smuggled state
# would otherwise validate and stay equal to and hash-identical with a clean proof while a downstream reader
# could still observe the smuggled attribute. The artifact namespace must therefore be exactly the seven
# declared keys and nothing else.
# ============================================================================================================
def _tainted_artifact(**extra_state: object) -> RoughtimeV19RequestInclusion:
    """Build a VALID seven-field artifact, then smuggle extra state past the frozen barrier."""
    artifact = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    for name, value in extra_state.items():
        object.__setattr__(artifact, name, value)
    return artifact


def test_verifier_produced_artifact_has_exactly_the_seven_expected_keys() -> None:
    request, response = _pair(path=(_FIXED_PATH_0,), directions=(RIGHT,))
    artifact = verify_roughtime_v19_request_inclusion(request, response)
    assert type(artifact.__dict__) is dict
    assert sorted(artifact.__dict__) == sorted(_EXPECTED_ARTIFACT_FIELDS)
    assert len(artifact.__dict__) == 7


def test_directly_constructed_valid_artifact_has_exactly_the_seven_expected_keys() -> None:
    artifact = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    assert sorted(artifact.__dict__) == sorted(_EXPECTED_ARTIFACT_FIELDS)
    assert artifact.computed_root.hex() == _FIXED_ROOT_INDEX_1_HEX


def test_overclaim_extra_state_rejected() -> None:
    """The exact finding: root_authentic = True must never survive validation."""
    tainted = _tainted_artifact(root_authentic=True)
    assert tainted.root_authentic is True
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion.__post_init__(tainted)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


@pytest.mark.parametrize(
    "extra",
    [
        {"root_authentic": True},
        {"signature_verified": True},
        {"provider_id": "cloudflare"},
        {"note": "innocuous"},
        {"_cache": {"trusted": True}},
        {"_memo": 1},
        {"root_authentic": True, "_cache": 0},
    ],
)
def test_every_extra_state_form_is_rejected(extra) -> None:
    tainted = _tainted_artifact(**extra)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion.__post_init__(tainted)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_non_str_namespace_key_rejected_without_raw_exception_leak() -> None:
    artifact = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    artifact.__dict__[42] = "foreign"
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion.__post_init__(artifact)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_str_subclass_namespace_key_rejected() -> None:
    class _Str(str):
        pass

    artifact = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    del artifact.__dict__["index"]
    artifact.__dict__[_Str("index")] = 1
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion.__post_init__(artifact)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_hostile_equality_key_rejected_before_its_eq_can_run() -> None:
    """A key whose __hash__ works but whose __eq__ is hostile survives insertion; it must never be compared."""
    eq_calls: list[str] = []

    class _HostileKey:
        def __hash__(self) -> int:
            return hash("index")

        def __eq__(self, other: object) -> bool:
            eq_calls.append("__eq__")
            return True

    artifact = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    del artifact.__dict__["index"]
    artifact.__dict__[_HostileKey()] = 1
    eq_calls.clear()
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion.__post_init__(artifact)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT
    assert eq_calls == []


def test_dict_subclass_namespace_rejected() -> None:
    """__dict__ accepts a dict SUBCLASS via object.__setattr__, which could lie about length or iteration."""

    class _Dict(dict):
        def __len__(self) -> int:
            return 7

    artifact = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    substituted = _Dict(artifact.__dict__)
    substituted["root_authentic"] = True
    object.__setattr__(artifact, "__dict__", substituted)
    assert type(artifact.__dict__) is not dict
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion.__post_init__(artifact)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_missing_declared_field_still_rejected() -> None:
    artifact = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    del artifact.__dict__["index"]
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion.__post_init__(artifact)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_renamed_declared_field_rejected() -> None:
    """Correct length and all-str keys, but the wrong inventory."""
    artifact = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    value = artifact.__dict__.pop("index")
    artifact.__dict__["indx"] = value
    assert len(artifact.__dict__) == 7
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion.__post_init__(artifact)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_hollow_exact_type_artifact_with_empty_namespace_rejected() -> None:
    hollow = object.__new__(RoughtimeV19RequestInclusion)
    with pytest.raises(RoughtimeV19RequestInclusionError) as excinfo:
        RoughtimeV19RequestInclusion.__post_init__(hollow)
    assert excinfo.value.reason is R.ARTIFACT_INCLUSION_INCONSISTENT


def test_clean_artifact_equality_and_hashing_unchanged() -> None:
    first = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    second = RoughtimeV19RequestInclusion(**_valid_artifact_fields())
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1


def test_production_declares_one_private_inclusion_field_inventory_in_order() -> None:
    inventory: list[str] = []
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_INCLUSION_FIELD_NAMES":
                    inventory = [element.value for element in node.value.elts]
    assert inventory == list(_EXPECTED_ARTIFACT_FIELDS)


def test_private_inventory_is_not_public_api() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    exports_block = source.split("__all__", 1)[1]
    assert "_INCLUSION_FIELD_NAMES" not in exports_block


def test_namespace_gate_does_not_use_slots() -> None:
    """The repair is a semantic namespace allowlist, not a slots-only rejection."""
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    assert "slots=True" not in source
    assert "__slots__" not in source
    assert RoughtimeV19RequestInclusion.__dict__.get("__slots__") is None


# ============================================================================================================
# Artifact sealing
# ============================================================================================================
_SEAL_LEDGER: list[str] = []


def _define_ordinary_subclass() -> type:
    class _Ordinary(RoughtimeV19RequestInclusion):
        pass

    return _Ordinary


def _define_post_init_subclass() -> type:
    class _NoValidation(RoughtimeV19RequestInclusion):
        def __post_init__(self) -> None:
            _SEAL_LEDGER.append("__post_init__")

    return _NoValidation


def _define_getattribute_subclass() -> type:
    class _Hostile(RoughtimeV19RequestInclusion):
        def __getattribute__(self, name: str) -> object:
            _SEAL_LEDGER.append("__getattribute__")
            return object.__getattribute__(self, name)

    return _Hostile


def _define_new_subclass() -> type:
    class _CustomNew(RoughtimeV19RequestInclusion):
        def __new__(cls, *args: object, **kwargs: object) -> object:
            _SEAL_LEDGER.append("__new__")
            return object.__new__(cls)

    return _CustomNew


def test_every_subclass_form_is_sealed_and_no_hostile_body_runs() -> None:
    _SEAL_LEDGER.clear()
    definers = (
        _define_ordinary_subclass,
        _define_post_init_subclass,
        _define_getattribute_subclass,
        _define_new_subclass,
    )
    for definer in definers:
        with pytest.raises(TypeError) as excinfo:
            definer()
        assert type(excinfo.value) is TypeError
        assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE
    with pytest.raises(TypeError) as excinfo:
        type("_Dynamic", (RoughtimeV19RequestInclusion,), {})
    assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE
    assert _SEAL_LEDGER == []


# ============================================================================================================
# Error contract
# ============================================================================================================
def test_reason_enum_is_exactly_five_members_in_order() -> None:
    assert tuple(member.value for member in RoughtimeV19RequestInclusionReason) == _EXPECTED_REASON_VALUES
    assert len(RoughtimeV19RequestInclusionReason) == 5


def test_reason_enum_has_no_path_invalid_member() -> None:
    assert not any("path" in member.value for member in RoughtimeV19RequestInclusionReason)
    assert not hasattr(RoughtimeV19RequestInclusionReason, "PATH_INVALID")


def test_error_str_is_exactly_reason_value() -> None:
    for member in RoughtimeV19RequestInclusionReason:
        assert str(RoughtimeV19RequestInclusionError(member)) == member.value


def test_error_reason_property_is_exact_member() -> None:
    error = RoughtimeV19RequestInclusionError(R.ROOT_MISMATCH)
    assert error.reason is R.ROOT_MISMATCH


@pytest.mark.parametrize("bad", ["root_mismatch", 0, None, object()])
def test_error_rejects_non_member_reason(bad) -> None:
    with pytest.raises(TypeError) as excinfo:
        RoughtimeV19RequestInclusionError(bad)
    assert str(excinfo.value) == _EXPECTED_REASON_TYPE_MESSAGE


def test_error_rejects_hostile_value_property_before_reading_it() -> None:
    read_attempts: list[str] = []

    class _HostileReason:
        @property
        def value(self) -> str:
            read_attempts.append("value")
            return "root_mismatch"

    with pytest.raises(TypeError) as excinfo:
        RoughtimeV19RequestInclusionError(_HostileReason())
    assert str(excinfo.value) == _EXPECTED_REASON_TYPE_MESSAGE
    assert read_attempts == []


@pytest.mark.parametrize("locked", ["reason", "_reason", "args"])
def test_error_locked_attributes_are_immutable(locked) -> None:
    error = RoughtimeV19RequestInclusionError(R.WRONG_INPUT_TYPE)
    with pytest.raises(AttributeError):
        setattr(error, locked, "tampered")
    with pytest.raises(AttributeError):
        delattr(error, locked)
    assert error.reason is R.WRONG_INPUT_TYPE


def test_error_is_runtime_error_subclass() -> None:
    assert issubclass(RoughtimeV19RequestInclusionError, RuntimeError)


# ============================================================================================================
# Profile, exports, artifact shape
# ============================================================================================================
def test_profile_id_is_exact() -> None:
    assert ROUGHTIME_V19_REQUEST_INCLUSION_PROFILE_ID == _EXPECTED_PROFILE_ID


def test_artifact_has_exactly_seven_fields_in_order() -> None:
    assert tuple(RoughtimeV19RequestInclusion.__dataclass_fields__) == _EXPECTED_ARTIFACT_FIELDS
    assert len(RoughtimeV19RequestInclusion.__dataclass_fields__) == 7


def test_artifact_carries_no_profile_field() -> None:
    assert "profile" not in RoughtimeV19RequestInclusion.__dataclass_fields__
    assert not any("profile" in name for name in RoughtimeV19RequestInclusion.__dataclass_fields__)


def test_artifact_field_names_avoid_every_forbidden_token() -> None:
    for name in RoughtimeV19RequestInclusion.__dataclass_fields__:
        for token in _FORBIDDEN_FIELD_TOKENS:
            assert token not in name


# ============================================================================================================
# AST and forbidden-surface checks on the production module
# ============================================================================================================
def _production_tree() -> ast.Module:
    return ast.parse(_PRODUCTION_PATH.read_text(encoding="utf-8"))


def test_production_import_allowlist_is_exact() -> None:
    modules: set[str] = set()
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    assert modules == {
        "__future__",
        "dataclasses",
        "enum",
        "hashlib",
        "crypto_core.validation.roughtime_v19_request_semantics",
        "crypto_core.validation.roughtime_v19_response_semantics",
    }


def test_production_imports_exactly_two_repository_modules() -> None:
    repository_modules = {
        node.module
        for node in ast.walk(_production_tree())
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("crypto_core")
    }
    assert repository_modules == {
        "crypto_core.validation.roughtime_v19_request_semantics",
        "crypto_core.validation.roughtime_v19_response_semantics",
    }


def test_production_imports_no_private_symbol() -> None:
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert not alias.name.startswith("_")


def test_production_imports_sha512_and_no_other_digest() -> None:
    imported: set[str] = set()
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.ImportFrom) and node.module == "hashlib":
            imported = {alias.name for alias in node.names}
    assert imported == {"sha512"}
    names = {node.id for node in ast.walk(_production_tree()) if isinstance(node, ast.Name)}
    for forbidden in ("sha256", "sha1", "md5", "blake2b", "shake_256"):
        assert forbidden not in names


def test_production_never_imports_forbidden_modules() -> None:
    forbidden = {
        "os",
        "sys",
        "socket",
        "subprocess",
        "threading",
        "datetime",
        "time",
        "secrets",
        "random",
        "json",
        "pathlib",
        "requests",
        "cryptography",
        "nacl",
        "ed25519",
        "crypto_core.validation.roughtime_v19_kernel",
        "crypto_core.validation.machine_time_source_registry",
        "crypto_core.validation.machine_time_policy",
    }
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden
                assert alias.name not in forbidden
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in forbidden
            assert module.split(".")[0] not in forbidden


def _verifier_function() -> ast.FunctionDef:
    for node in _production_tree().body:
        if isinstance(node, ast.FunctionDef) and node.name == "verify_roughtime_v19_request_inclusion":
            return node
    raise AssertionError("verifier function not found")


def test_verifier_never_reads_an_attribute_of_a_caller_supplied_artifact() -> None:
    """Every value feeding the fold must come from the canonical reparse, never from the caller's object.

    Complete revalidation already proves the caller's declared state equals its own raw, so reading a caller
    attribute would agree today. This structural assertion is what keeps the two controls independent: it fails
    the moment the computation is rewired to the caller, even while revalidation still happens to pass.
    """
    caller_reads = [
        node.attr
        for node in ast.walk(_verifier_function())
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in {"request", "response"}
    ]
    assert caller_reads == []


def test_verifier_computation_reads_only_canonical_reparsed_artifacts() -> None:
    """Only the reason enum and the two canonical reparsed artifacts may be attribute-read in the verifier."""
    artifact_reads = {
        node.value.id
        for node in ast.walk(_verifier_function())
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id != "RoughtimeV19RequestInclusionReason"
    }
    assert artifact_reads == {"canonical_request", "canonical_response"}
    attributes = {
        node.attr
        for node in ast.walk(_verifier_function())
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id != "RoughtimeV19RequestInclusionReason"
    }
    assert attributes == {"raw", "path", "index", "signed_response"}


def test_production_declares_exactly_five_public_exports() -> None:
    exports: list[str] = []
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    exports = [element.value for element in node.value.elts]
    assert exports == [
        "ROUGHTIME_V19_REQUEST_INCLUSION_PROFILE_ID",
        "RoughtimeV19RequestInclusion",
        "RoughtimeV19RequestInclusionError",
        "RoughtimeV19RequestInclusionReason",
        "verify_roughtime_v19_request_inclusion",
    ]
    assert len(exports) == 5


def test_production_defines_exactly_five_reason_members() -> None:
    members: list[str] = []
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.ClassDef) and node.name == "RoughtimeV19RequestInclusionReason":
            for statement in node.body:
                if isinstance(statement, ast.Assign):
                    for target in statement.targets:
                        if isinstance(target, ast.Name):
                            members.append(statement.value.value)
    assert members == list(_EXPECTED_REASON_VALUES)


def test_production_never_catches_base_exception() -> None:
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            names = [child.id for child in ast.walk(node.type) if isinstance(child, ast.Name)]
            for forbidden in ("BaseException", "KeyboardInterrupt", "SystemExit", "GeneratorExit", "Exception"):
                assert forbidden not in names


def test_production_uses_no_isinstance_for_input_gating() -> None:
    calls = {
        node.func.id
        for node in ast.walk(_production_tree())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "isinstance" not in calls


def test_production_mentions_no_signature_or_key_verification_symbol() -> None:
    names = {node.id for node in ast.walk(_production_tree()) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(_production_tree()) if isinstance(node, ast.Attribute)}
    for forbidden in ("verify_signature", "Ed25519PublicKey", "signing_key", "srv_hash", "verify_key"):
        assert forbidden not in names
        assert forbidden not in attributes


def test_production_reads_no_nonce_or_version_attribute() -> None:
    attributes = {node.attr for node in ast.walk(_production_tree()) if isinstance(node, ast.Attribute)}
    assert "nonce" not in attributes
    assert "versions" not in attributes
    assert "version" not in attributes


def test_production_defines_exactly_the_expected_public_classes_and_function() -> None:
    tree = _production_tree()
    classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert classes == [
        "RoughtimeV19RequestInclusionReason",
        "RoughtimeV19RequestInclusionError",
        "RoughtimeV19RequestInclusion",
    ]
    assert "verify_roughtime_v19_request_inclusion" in functions
    assert [name for name in functions if not name.startswith("_")] == ["verify_roughtime_v19_request_inclusion"]


def test_production_artifact_declares_seven_annotated_fields() -> None:
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.ClassDef) and node.name == "RoughtimeV19RequestInclusion":
            annotated = [
                statement.target.id
                for statement in node.body
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
            ]
            assert annotated == list(_EXPECTED_ARTIFACT_FIELDS)
            return
    raise AssertionError("artifact class not found")


def test_production_seals_the_artifact_at_definition_time() -> None:
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.ClassDef) and node.name == "RoughtimeV19RequestInclusion":
            methods = [statement.name for statement in node.body if isinstance(statement, ast.FunctionDef)]
            assert "__init_subclass__" in methods
            assert "__post_init__" in methods
            return
    raise AssertionError("artifact class not found")


def test_k1_k2_k3_modules_remain_importable_and_unreferenced_privately() -> None:
    """K4 must never reach into a merged module's private surface."""
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    for private in ("_decode_response_primitive", "_decode_request_primitive", "_validate_response_state"):
        assert private not in source


def test_reference_to_unused_field_helper_names_is_stable() -> None:
    """The K3/K2 declared inventories the verifier revalidates must stay complete."""
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    for name in ("versions", "server_key_id", "padding", "signed_response", "certificate"):
        assert name in source
    assert RoughtimeV19Field is not None
