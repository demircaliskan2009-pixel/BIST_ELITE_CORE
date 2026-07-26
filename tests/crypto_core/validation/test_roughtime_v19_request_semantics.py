"""Deterministic contract tests for the Roughtime draft-19 bounded REQUEST semantic decoder (K3).

All fixtures are built by TEST-ONLY encoders (``_encode_message`` / ``_encode_packet``) that are independent
of the production decoder, so positive expectations are never proven by the code under test. Constants
(profile id, tag identities, field lengths, reason inventory) are pinned independently here.

Alignment note (inherited K1 contract): K1 requires every message value except the LAST one (in canonical tag
order) to end on a four-byte boundary, because the explicit offsets must be four-byte aligned. Canonical
request tag order by little-endian uint32 is ``PAD`` < ``VER`` < ``SRV`` < ``NONC`` < ``TYPE`` < ``ZZZZ``.
Consequences used throughout this file:

* ``TYPE`` is last in a mandatory-only request, so odd ``TYPE`` lengths reach the ``request_type_invalid``
  reason directly;
* ``ZZZZ`` sorts last overall, so any ``ZZZZ`` length (including zero and non-aligned) is reachable;
* ``NONC`` and ``SRV`` are never last, so lengths 31/33 break K1 offset alignment and normalize to
  ``request_structural_invalid``; their field-specific reasons are proven with four-aligned wrong lengths
  (28/36), which K1 accepts and the semantic layer then rejects. Both paths are asserted;
* a non-divisible ``VER`` length likewise surfaces as ``request_structural_invalid``; the production
  divisibility check is retained as defence in depth and is documented as such.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from crypto_core.validation.roughtime_v19_kernel import (
    RoughtimeV19Field,
    parse_roughtime_v19_packet,
)
from crypto_core.validation.roughtime_v19_request_semantics import (
    ROUGHTIME_V19_REQUEST_SEMANTIC_PROFILE_ID,
    RoughtimeV19RequestSemanticError,
    RoughtimeV19RequestSemanticReason,
    RoughtimeV19RequestSemantics,
    parse_roughtime_v19_request,
)

R = RoughtimeV19RequestSemanticReason

# --- Independently pinned identity constants --------------------------------------------------------------
_EXPECTED_REQUEST_PROFILE_ID = "roughtime-v19-request-semantic-bounded-k3.v1"
_MAGIC = b"ROUGHTIM"

_TAG_VER = b"VER\x00"
_TAG_NONC = b"NONC"
_TAG_TYPE = b"TYPE"
_TAG_SRV = b"SRV\x00"
_TAG_ZZZZ = b"ZZZZ"
_TAG_PAD = b"PAD\x00"  # old-draft padding tag: must be an UNKNOWN extension here, never `padding`

_EXT_A = b"A\x00\x00\x00"  # canonical one-letter tag; smallest uint32, sorts first
_EXT_YY = b"YY\x00\x00"  # canonical two-letter tag; sorts early
_EXT_AAAA = b"AAAA"  # canonical four-letter tag; sorts between SRV and NONC

_NONC_BYTES = 32
_SRV_BYTES = 32
_VER_ENTRY_BYTES = 4
_MAX_VER_ENTRIES = 32
_K1_MAX_PACKET_BYTES = 4096
_K1_MAX_MESSAGE_BYTES = 4084

_VALID_NONCE = bytes(range(_NONC_BYTES))
_ZERO_NONCE = b"\x00" * _NONC_BYTES
_VALID_SRV = bytes(range(100, 100 + _SRV_BYTES))


# --- Test-only encoders (independent of production) -------------------------------------------------------
def _le(tag: bytes) -> int:
    return int.from_bytes(tag, "little")


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "little")


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


def _encode_packet(pairs: list[tuple[bytes, bytes]]) -> bytes:
    message = _encode_message(pairs)
    return _MAGIC + _u32(len(message)) + message


def _ver_value(versions: list[int]) -> bytes:
    return b"".join(_u32(version) for version in versions)


def _pairs(
    *,
    versions: list[int] | None = None,
    ver_value: bytes | None = None,
    nonce: bytes | None = None,
    type_value: bytes | None = None,
    srv: bytes | None = None,
    zzzz: bytes | None = None,
    extra: list[tuple[bytes, bytes]] | None = None,
    drop: tuple[bytes, ...] = (),
) -> list[tuple[bytes, bytes]]:
    """Build request (tag, value) pairs, defaulting to a minimal valid mandatory-only request."""
    built: list[tuple[bytes, bytes]] = []
    if _TAG_VER not in drop:
        built.append((_TAG_VER, ver_value if ver_value is not None else _ver_value(versions or [1])))
    if _TAG_NONC not in drop:
        built.append((_TAG_NONC, nonce if nonce is not None else _VALID_NONCE))
    if _TAG_TYPE not in drop:
        built.append((_TAG_TYPE, type_value if type_value is not None else _u32(0)))
    if srv is not None:
        built.append((_TAG_SRV, srv))
    if zzzz is not None:
        built.append((_TAG_ZZZZ, zzzz))
    if extra:
        built.extend(extra)
    return built


def _packet(**kwargs: object) -> bytes:
    return _encode_packet(_pairs(**kwargs))  # type: ignore[arg-type]


def _reason(excinfo: pytest.ExceptionInfo[RoughtimeV19RequestSemanticError]) -> RoughtimeV19RequestSemanticReason:
    return excinfo.value.reason


# =========================================================================================================
# 1. Mandatory-only valid request
# =========================================================================================================
def test_profile_id_is_pinned() -> None:
    assert ROUGHTIME_V19_REQUEST_SEMANTIC_PROFILE_ID == _EXPECTED_REQUEST_PROFILE_ID


def test_mandatory_only_request_parses() -> None:
    request = parse_roughtime_v19_request(_packet())
    assert request.versions == (1,)
    assert request.nonce == _VALID_NONCE
    assert request.message_type == 0
    assert request.server_key_id is None
    assert request.padding is None
    assert request.extensions == ()


def test_mandatory_only_request_preserves_exact_raw() -> None:
    packet = _packet()
    request = parse_roughtime_v19_request(packet)
    assert request.raw == packet
    assert request.raw is packet  # exact bytes preserved, never reconstructed


# =========================================================================================================
# 2. Full request with SRV, ZZZZ and multiple unknown extensions
# =========================================================================================================
def _full_packet() -> bytes:
    return _packet(
        versions=[1, 2, 0x80000000],
        srv=_VALID_SRV,
        zzzz=b"\x00" * 8,
        extra=[(_EXT_A, b"\x01\x02\x03\x04"), (_EXT_YY, b""), (_EXT_AAAA, b"\xff" * 4)],
    )


def test_full_request_parses_every_known_field() -> None:
    request = parse_roughtime_v19_request(_full_packet())
    assert request.versions == (1, 2, 0x80000000)
    assert request.nonce == _VALID_NONCE
    assert request.message_type == 0
    assert request.server_key_id == _VALID_SRV
    assert request.padding == b"\x00" * 8


def test_full_request_extensions_preserved_in_canonical_order() -> None:
    request = parse_roughtime_v19_request(_full_packet())
    # Canonical ascending uint32 order: A < YY < AAAA. Known tags never appear as extensions.
    assert tuple(field.tag for field in request.extensions) == (_EXT_A, _EXT_YY, _EXT_AAAA)
    assert tuple(field.value for field in request.extensions) == (b"\x01\x02\x03\x04", b"", b"\xff" * 4)
    for field in request.extensions:
        assert type(field) is RoughtimeV19Field


def test_known_tags_never_appear_in_extensions() -> None:
    request = parse_roughtime_v19_request(_full_packet())
    tags = {field.tag for field in request.extensions}
    assert tags.isdisjoint({_TAG_VER, _TAG_NONC, _TAG_TYPE, _TAG_SRV, _TAG_ZZZZ})


# =========================================================================================================
# 3. Repeated-parse equality and hashing
# =========================================================================================================
def test_repeated_parse_is_equal_and_hashable() -> None:
    packet = _full_packet()
    first = parse_roughtime_v19_request(packet)
    second = parse_roughtime_v19_request(packet)
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1


def test_distinct_requests_are_unequal() -> None:
    assert parse_roughtime_v19_request(_packet()) != parse_roughtime_v19_request(_packet(versions=[2]))


# =========================================================================================================
# 4. Missing mandatory tags, independently
# =========================================================================================================
@pytest.mark.parametrize("dropped", [_TAG_VER, _TAG_NONC, _TAG_TYPE])
def test_missing_mandatory_tag_rejected(dropped: bytes) -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(drop=(dropped,)))
    assert _reason(excinfo) is R.REQUEST_MISSING_MANDATORY_TAG


def test_missing_mandatory_tag_precedes_optional_validation() -> None:
    # An invalid SRV is present, but a missing mandatory tag is reported first (pinned precedence).
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(drop=(_TAG_VER,), srv=b"\x00" * 28))
    assert _reason(excinfo) is R.REQUEST_MISSING_MANDATORY_TAG


# =========================================================================================================
# 5. VER semantics
# =========================================================================================================
def test_ver_single_entry_accepted() -> None:
    assert parse_roughtime_v19_request(_packet(versions=[7])).versions == (7,)


def test_ver_thirty_two_entries_accepted() -> None:
    versions = list(range(1, _MAX_VER_ENTRIES + 1))
    assert parse_roughtime_v19_request(_packet(versions=versions)).versions == tuple(versions)


def test_ver_ascending_accepted() -> None:
    assert parse_roughtime_v19_request(_packet(versions=[1, 5, 9])).versions == (1, 5, 9)


def test_ver_max_uint32_accepted() -> None:
    assert parse_roughtime_v19_request(_packet(versions=[1, 0xFFFFFFFF])).versions == (1, 0xFFFFFFFF)


def test_ver_unknown_only_versions_accepted() -> None:
    # No specific version is required; unknown declared versions are valid.
    assert parse_roughtime_v19_request(_packet(versions=[0x0A0A0A0A])).versions == (0x0A0A0A0A,)


def test_ver_empty_rejected() -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(ver_value=b""))
    assert _reason(excinfo) is R.REQUEST_VER_INVALID


def test_ver_thirty_three_entries_rejected() -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(versions=list(range(1, _MAX_VER_ENTRIES + 2))))
    assert _reason(excinfo) is R.REQUEST_VER_INVALID


def test_ver_duplicate_rejected() -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(versions=[1, 1]))
    assert _reason(excinfo) is R.REQUEST_VER_INVALID


def test_ver_adjacent_duplicate_inside_longer_list_rejected() -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(versions=[1, 4, 4, 9]))
    assert _reason(excinfo) is R.REQUEST_VER_INVALID


def test_ver_descending_rejected() -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(versions=[9, 1]))
    assert _reason(excinfo) is R.REQUEST_VER_INVALID


def test_ver_non_divisible_length_normalizes_to_structural() -> None:
    # VER is never last in canonical order (NONC/TYPE follow), so a non-divisible length breaks K1 offset
    # alignment and is reported structurally. The production divisibility check remains as defence in depth.
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(ver_value=b"\x01\x00\x00\x00\x02"))
    assert _reason(excinfo) is R.REQUEST_STRUCTURAL_INVALID


# =========================================================================================================
# 6. NONC validation
# =========================================================================================================
def test_nonce_exact_thirty_two_accepted_and_preserved() -> None:
    request = parse_roughtime_v19_request(_packet(nonce=_VALID_NONCE))
    assert request.nonce == _VALID_NONCE
    assert len(request.nonce) == _NONC_BYTES


def test_all_zero_nonce_is_valid() -> None:
    # No randomness is evaluated: an all-zero nonce is structurally and semantically valid here.
    assert parse_roughtime_v19_request(_packet(nonce=_ZERO_NONCE)).nonce == _ZERO_NONCE


@pytest.mark.parametrize("length", [28, 36])
def test_nonce_four_aligned_wrong_length_rejected(length: int) -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(nonce=b"\x01" * length))
    assert _reason(excinfo) is R.REQUEST_NONC_INVALID


@pytest.mark.parametrize("length", [31, 33])
def test_nonce_non_aligned_wrong_length_normalizes_to_structural(length: int) -> None:
    # NONC is never last (TYPE follows), so 31/33 break K1 offset alignment before the semantic length rule.
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(nonce=b"\x01" * length))
    assert _reason(excinfo) is R.REQUEST_STRUCTURAL_INVALID


def test_nonce_empty_rejected() -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(nonce=b""))
    assert _reason(excinfo) is R.REQUEST_NONC_INVALID


# =========================================================================================================
# 7. TYPE validation
# =========================================================================================================
def test_type_zero_accepted() -> None:
    assert parse_roughtime_v19_request(_packet(type_value=_u32(0))).message_type == 0


def test_type_one_rejected() -> None:
    # 1 is the RESPONSE type; a request declaring it is invalid.
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(type_value=_u32(1)))
    assert _reason(excinfo) is R.REQUEST_TYPE_INVALID


def test_type_max_uint32_rejected() -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(type_value=_u32(0xFFFFFFFF)))
    assert _reason(excinfo) is R.REQUEST_TYPE_INVALID


@pytest.mark.parametrize("value", [b"", b"\x00", b"\x00\x00\x00", b"\x00\x00\x00\x00\x00", b"\x00" * 8])
def test_type_wrong_length_rejected(value: bytes) -> None:
    # TYPE is last in a mandatory-only request, so any length reaches the semantic rule directly.
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(type_value=value))
    assert _reason(excinfo) is R.REQUEST_TYPE_INVALID


# =========================================================================================================
# 8. SRV validation
# =========================================================================================================
def test_srv_absent_is_none() -> None:
    assert parse_roughtime_v19_request(_packet()).server_key_id is None


def test_srv_valid_thirty_two_preserved_exactly() -> None:
    request = parse_roughtime_v19_request(_packet(srv=_VALID_SRV))
    assert request.server_key_id == _VALID_SRV  # exact bytes; never hashed, never provider-bound


def test_srv_all_zero_is_valid() -> None:
    assert parse_roughtime_v19_request(_packet(srv=b"\x00" * _SRV_BYTES)).server_key_id == b"\x00" * _SRV_BYTES


@pytest.mark.parametrize("length", [0, 28, 36])
def test_srv_four_aligned_wrong_length_rejected(length: int) -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(srv=b"\x02" * length))
    assert _reason(excinfo) is R.REQUEST_SRV_INVALID


@pytest.mark.parametrize("length", [31, 33])
def test_srv_non_aligned_wrong_length_normalizes_to_structural(length: int) -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(srv=b"\x02" * length))
    assert _reason(excinfo) is R.REQUEST_STRUCTURAL_INVALID


# =========================================================================================================
# 9. ZZZZ validation
# =========================================================================================================
def test_zzzz_absent_is_none() -> None:
    assert parse_roughtime_v19_request(_packet()).padding is None


def test_zzzz_present_empty_is_distinct_from_absent() -> None:
    present = parse_roughtime_v19_request(_packet(zzzz=b""))
    absent = parse_roughtime_v19_request(_packet())
    assert present.padding == b""
    assert present.padding is not None
    assert absent.padding is None
    assert present.padding != absent.padding


@pytest.mark.parametrize("length", [1, 4, 7, 64, 512])
def test_zzzz_all_zero_accepted(length: int) -> None:
    assert parse_roughtime_v19_request(_packet(zzzz=b"\x00" * length)).padding == b"\x00" * length


@pytest.mark.parametrize(
    "value",
    [
        b"\x01" + b"\x00" * 7,  # non-zero at the beginning
        b"\x00" * 4 + b"\x01" + b"\x00" * 3,  # non-zero in the middle
        b"\x00" * 7 + b"\x01",  # non-zero at the end
        b"\xff",
    ],
)
def test_zzzz_non_zero_byte_rejected(value: bytes) -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(zzzz=value))
    assert _reason(excinfo) is R.REQUEST_ZZZZ_INVALID


# =========================================================================================================
# 10-13. Size policy: transport minimum is advisory, K1 bounds are inherited
# =========================================================================================================
def test_short_request_well_below_1024_accepted() -> None:
    packet = _packet()
    assert len(packet) < 200  # far below the advisory UDP floor
    assert parse_roughtime_v19_request(packet).message_type == 0


def _packet_with_message_length(target_message_bytes: int) -> bytes:
    """Build a valid request whose MESSAGE length is exactly ``target_message_bytes`` using ZZZZ padding."""
    base = _packet(zzzz=b"")
    base_message_length = len(base) - len(_MAGIC) - 4
    pad = target_message_bytes - base_message_length
    assert pad >= 0
    return _packet(zzzz=b"\x00" * pad)


def test_request_message_exactly_1024_bytes_accepted() -> None:
    packet = _packet_with_message_length(1024)
    assert len(packet) - len(_MAGIC) - 4 == 1024
    request = parse_roughtime_v19_request(packet)
    assert request.padding is not None
    assert request.padding.count(0) == len(request.padding)


def test_request_message_above_1024_inside_k1_bounds_accepted() -> None:
    packet = _packet_with_message_length(2048)
    assert len(packet) <= _K1_MAX_PACKET_BYTES
    assert parse_roughtime_v19_request(packet).message_type == 0


def test_request_outside_k1_profile_normalizes_to_structural() -> None:
    packet = _packet(zzzz=b"\x00" * (_K1_MAX_MESSAGE_BYTES + 64))
    assert len(packet) > _K1_MAX_PACKET_BYTES
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(packet)
    assert _reason(excinfo) is R.REQUEST_STRUCTURAL_INVALID


# =========================================================================================================
# 14. Old-draft PAD regression: PAD is an UNKNOWN extension, never `padding`
# =========================================================================================================
@pytest.mark.parametrize("pad_value", [b"\x00" * 4, b"\xff" * 4, b"\x01\x02\x03\x04", b""])
def test_pad_is_preserved_as_unknown_extension(pad_value: bytes) -> None:
    request = parse_roughtime_v19_request(_packet(extra=[(_TAG_PAD, pad_value)]))
    assert request.padding is None  # PAD never populates the draft-19 ZZZZ padding field
    assert len(request.extensions) == 1
    assert request.extensions[0].tag == _TAG_PAD
    assert request.extensions[0].value == pad_value


def test_pad_non_zero_value_is_not_validated_as_padding() -> None:
    # A non-zero PAD is accepted: PAD carries no draft-19 padding semantics here.
    request = parse_roughtime_v19_request(_packet(extra=[(_TAG_PAD, b"\xff\xff\xff\xff")]))
    assert request.extensions[0].value == b"\xff\xff\xff\xff"
    assert request.padding is None


def test_pad_and_zzzz_coexist_independently() -> None:
    request = parse_roughtime_v19_request(_packet(zzzz=b"\x00" * 4, extra=[(_TAG_PAD, b"\xab" * 4)]))
    assert request.padding == b"\x00" * 4  # only ZZZZ populates padding
    assert tuple(field.tag for field in request.extensions) == (_TAG_PAD,)
    assert request.extensions[0].value == b"\xab" * 4


# =========================================================================================================
# 15. Unknown extension policy
# =========================================================================================================
def test_unknown_tags_of_varied_shapes_preserved_in_canonical_order() -> None:
    request = parse_roughtime_v19_request(
        _packet(extra=[(_EXT_AAAA, b"\x09" * 8), (_EXT_A, b""), (_EXT_YY, b"\x00\x00\x00\x00")])
    )
    assert tuple(field.tag for field in request.extensions) == (_EXT_A, _EXT_YY, _EXT_AAAA)
    assert tuple(field.value for field in request.extensions) == (b"", b"\x00\x00\x00\x00", b"\x09" * 8)


def test_unknown_extension_values_are_opaque() -> None:
    # An unknown tag whose value looks like a version list is not interpreted.
    request = parse_roughtime_v19_request(_packet(extra=[(_EXT_YY, _ver_value([9, 9, 9]))]))
    assert request.versions == (1,)
    assert request.extensions[0].value == _ver_value([9, 9, 9])


# =========================================================================================================
# 16. Exact public input-type rejection
# =========================================================================================================
class _BytesSubclass(bytes):
    pass


@pytest.mark.parametrize(
    "candidate",
    [
        None,
        0,
        1.0,
        True,
        "ROUGHTIM",
        [],
        {},
        (),
        object(),
        bytearray(_packet()),
        memoryview(_packet()),
        _BytesSubclass(_packet()),
    ],
)
def test_public_input_must_be_exact_bytes(candidate: object) -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(candidate)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.WRONG_INPUT_TYPE


# =========================================================================================================
# 17-19. Direct artifact construction and per-field mismatch
# =========================================================================================================
def _decoded_parts(packet: bytes) -> dict[bytes, RoughtimeV19Field]:
    """Independently decode a packet through the K1 public parser (a dependency, not the code under test)."""
    parsed = parse_roughtime_v19_packet(packet)
    return {field.tag: field for field in parsed.message.fields}


def _independent_artifact(packet: bytes) -> RoughtimeV19RequestSemantics:
    """Construct the artifact directly from independently decoded K1 state (no K3 parser involved)."""
    by_tag = _decoded_parts(packet)
    ver_value = by_tag[_TAG_VER].value
    versions = tuple(
        int.from_bytes(ver_value[index * _VER_ENTRY_BYTES : (index + 1) * _VER_ENTRY_BYTES], "little")
        for index in range(len(ver_value) // _VER_ENTRY_BYTES)
    )
    known = {_TAG_VER, _TAG_NONC, _TAG_TYPE, _TAG_SRV, _TAG_ZZZZ}
    parsed = parse_roughtime_v19_packet(packet)
    return RoughtimeV19RequestSemantics(
        versions=versions,
        nonce=by_tag[_TAG_NONC].value,
        message_type=int.from_bytes(by_tag[_TAG_TYPE].value, "little"),
        server_key_id=by_tag[_TAG_SRV].value if _TAG_SRV in by_tag else None,
        padding=by_tag[_TAG_ZZZZ].value if _TAG_ZZZZ in by_tag else None,
        extensions=tuple(field for field in parsed.message.fields if field.tag not in known),
        raw=packet,
    )


def test_independent_direct_construction_matches_parser() -> None:
    packet = _full_packet()
    assert _independent_artifact(packet) == parse_roughtime_v19_request(packet)


def test_independent_direct_construction_mandatory_only() -> None:
    packet = _packet()
    assert _independent_artifact(packet) == parse_roughtime_v19_request(packet)


def _base_kwargs(packet: bytes) -> dict[str, object]:
    request = parse_roughtime_v19_request(packet)
    return {
        "versions": request.versions,
        "nonce": request.nonce,
        "message_type": request.message_type,
        "server_key_id": request.server_key_id,
        "padding": request.padding,
        "extensions": request.extensions,
        "raw": request.raw,
    }


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("versions", (2,)),
        ("versions", ()),
        ("versions", (1, 2)),
        ("nonce", b"\x09" * 32),
        ("message_type", 1),
        ("server_key_id", b"\x07" * 32),
        ("padding", b"\x00" * 4),  # _full_packet() carries eight zero padding bytes
        ("extensions", ()),
    ],
)
def test_artifact_field_mismatch_rejected(field: str, bad_value: object) -> None:
    kwargs = _base_kwargs(_full_packet())
    kwargs[field] = bad_value
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


def test_artifact_absent_optional_cannot_be_claimed_present() -> None:
    kwargs = _base_kwargs(_packet())  # SRV and ZZZZ absent
    kwargs["server_key_id"] = b"\x00" * 32
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


def test_artifact_present_empty_padding_cannot_be_claimed_absent() -> None:
    kwargs = _base_kwargs(_packet(zzzz=b""))
    kwargs["padding"] = None
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


def test_artifact_absent_padding_cannot_be_claimed_present_empty() -> None:
    kwargs = _base_kwargs(_packet())
    kwargs["padding"] = b""
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("versions", [1]),  # list, not tuple
        ("versions", (True,)),  # bool is an int subclass
        ("nonce", bytearray(_VALID_NONCE)),
        ("nonce", _BytesSubclass(_VALID_NONCE)),
        ("message_type", False),  # bool is an int subclass
        ("server_key_id", 0),
        ("padding", 0),
        ("extensions", []),
        ("raw", bytearray(_packet())),
        ("raw", _BytesSubclass(_packet())),
    ],
)
def test_artifact_wrong_component_type_rejected(field: str, bad_value: object) -> None:
    kwargs = _base_kwargs(_packet())
    kwargs[field] = bad_value
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


def test_artifact_malformed_raw_rejected() -> None:
    kwargs = _base_kwargs(_packet())
    kwargs["raw"] = b"not-a-roughtime-packet"
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


# =========================================================================================================
# 20. Incomplete / hollow exact-type extensions must close safely
# =========================================================================================================
def test_hollow_exact_type_extension_rejected_without_raw_exception() -> None:
    kwargs = _base_kwargs(_full_packet())
    hollow = object.__new__(RoughtimeV19Field)  # exact type, initializer never ran
    assert type(hollow) is RoughtimeV19Field
    kwargs["extensions"] = (hollow,) + tuple(kwargs["extensions"])[1:]  # type: ignore[arg-type]
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


def test_partially_populated_exact_type_extension_rejected() -> None:
    kwargs = _base_kwargs(_full_packet())
    partial = object.__new__(RoughtimeV19Field)
    object.__setattr__(partial, "tag", _EXT_A)  # tag_uint32 and value still missing
    kwargs["extensions"] = (partial,) + tuple(kwargs["extensions"])[1:]  # type: ignore[arg-type]
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


def test_exact_type_extension_with_inconsistent_tag_uint32_rejected() -> None:
    kwargs = _base_kwargs(_full_packet())
    forged = object.__new__(RoughtimeV19Field)
    object.__setattr__(forged, "tag", _EXT_A)
    object.__setattr__(forged, "tag_uint32", 999999)  # not int.from_bytes(tag, "little")
    object.__setattr__(forged, "value", b"\x01\x02\x03\x04")
    kwargs["extensions"] = (forged,) + tuple(kwargs["extensions"])[1:]  # type: ignore[arg-type]
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


def test_exact_type_extension_with_non_canonical_tag_rejected() -> None:
    kwargs = _base_kwargs(_full_packet())
    forged = object.__new__(RoughtimeV19Field)
    object.__setattr__(forged, "tag", b"\x00\x00\x00\x00")  # non-canonical
    object.__setattr__(forged, "tag_uint32", 0)
    object.__setattr__(forged, "value", b"\x01\x02\x03\x04")
    kwargs["extensions"] = (forged,) + tuple(kwargs["extensions"])[1:]  # type: ignore[arg-type]
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


class _FieldSubclass(RoughtimeV19Field):
    pass


def test_extension_field_subclass_rejected() -> None:
    kwargs = _base_kwargs(_full_packet())
    original = tuple(kwargs["extensions"])[0]  # type: ignore[arg-type]
    clone = _FieldSubclass(tag=original.tag, tag_uint32=original.tag_uint32, value=original.value)
    kwargs["extensions"] = (clone,) + tuple(kwargs["extensions"])[1:]  # type: ignore[arg-type]
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


def test_extension_count_mismatch_rejected() -> None:
    kwargs = _base_kwargs(_full_packet())
    kwargs["extensions"] = tuple(kwargs["extensions"])[:-1]  # type: ignore[arg-type]
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


# =========================================================================================================
# 21. K1 structural error normalization
# =========================================================================================================
@pytest.mark.parametrize(
    "packet",
    [
        b"",
        b"\x00" * 4,
        b"NOTMAGIC" + _u32(4) + b"\x01\x00\x00\x00",
        _MAGIC + _u32(999) + _encode_message(_pairs()),  # declared length mismatch
        _MAGIC + _u32(4) + b"\x00\x00\x00\x00",  # pair count zero
        _MAGIC[:6],
    ],
)
def test_k1_structural_failures_normalize(packet: bytes) -> None:
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(packet)
    assert _reason(excinfo) is R.REQUEST_STRUCTURAL_INVALID


def test_no_kernel_error_leaks_from_public_parser() -> None:
    from crypto_core.validation.roughtime_v19_kernel import RoughtimeV19KernelError

    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(b"\x00" * 16)
    assert not isinstance(excinfo.value, RoughtimeV19KernelError)


# =========================================================================================================
# 22. Closed nine-member reason inventory and error immutability
# =========================================================================================================
def test_reason_inventory_is_exactly_nine_pinned_members() -> None:
    assert [member.value for member in R] == [
        "wrong_input_type",
        "request_structural_invalid",
        "request_missing_mandatory_tag",
        "request_ver_invalid",
        "request_nonc_invalid",
        "request_type_invalid",
        "request_srv_invalid",
        "request_zzzz_invalid",
        "artifact_request_inconsistent",
    ]
    assert len(R) == 9


def test_error_str_is_exactly_reason_value() -> None:
    for member in R:
        error = RoughtimeV19RequestSemanticError(member)
        assert str(error) == member.value
        assert error.reason is member


@pytest.mark.parametrize("candidate", [None, "wrong_input_type", 0, object()])
def test_error_constructor_requires_exact_reason_member(candidate: object) -> None:
    with pytest.raises(TypeError):
        RoughtimeV19RequestSemanticError(candidate)  # type: ignore[arg-type]


def test_error_constructor_never_reads_hostile_value_property() -> None:
    accessed: list[str] = []

    class _Hostile:
        @property
        def value(self) -> str:
            accessed.append("value")
            raise AssertionError("value must never be read")

    with pytest.raises(TypeError):
        RoughtimeV19RequestSemanticError(_Hostile())  # type: ignore[arg-type]
    assert accessed == []


def test_error_is_immutable_after_construction() -> None:
    error = RoughtimeV19RequestSemanticError(R.WRONG_INPUT_TYPE)
    for attribute in ("reason", "_reason", "args"):
        with pytest.raises(AttributeError):
            setattr(error, attribute, "tampered")
        with pytest.raises(AttributeError):
            delattr(error, attribute)
    assert error.reason is R.WRONG_INPUT_TYPE
    assert str(error) == "wrong_input_type"


# =========================================================================================================
# 23. Frozen artifact
# =========================================================================================================
@pytest.mark.parametrize(
    "attribute",
    ["versions", "nonce", "message_type", "server_key_id", "padding", "extensions", "raw"],
)
def test_artifact_is_frozen(attribute: str) -> None:
    request = parse_roughtime_v19_request(_full_packet())
    with pytest.raises(Exception):  # noqa: B017 - dataclasses raises FrozenInstanceError
        setattr(request, attribute, None)
    with pytest.raises(Exception):  # noqa: B017
        delattr(request, attribute)


# =========================================================================================================
# 24. Sealed public artifact — no subclass may enter the trusted artifact boundary
# =========================================================================================================
_EXPECTED_SEAL_MESSAGE = "RoughtimeV19RequestSemantics is a sealed artifact type and cannot be subclassed"


def test_exact_base_valid_construction_still_succeeds() -> None:
    # Sealing must not disturb the legitimate exact-base path.
    packet = _full_packet()
    assert _independent_artifact(packet) == parse_roughtime_v19_request(packet)


def test_exact_base_inconsistent_construction_still_closed() -> None:
    kwargs = _base_kwargs(_full_packet())
    kwargs["nonce"] = b"\xff" * 32
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics(**kwargs)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


def test_parser_output_is_exactly_the_base_type() -> None:
    assert type(parse_roughtime_v19_request(_full_packet())) is RoughtimeV19RequestSemantics


def test_ordinary_subclass_definition_is_rejected() -> None:
    with pytest.raises(TypeError) as excinfo:

        class _Ordinary(RoughtimeV19RequestSemantics):
            pass

    assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE


def test_subclass_overriding_post_init_cannot_be_defined() -> None:
    # The pre-repair bypass: overriding __post_init__ skipped base validation entirely and admitted an
    # instance whose declared fields did not match its own raw bytes. Sealing fires first, at class
    # definition, so the override can never exist.
    with pytest.raises(TypeError) as excinfo:

        class _NoValidation(RoughtimeV19RequestSemantics):
            def __post_init__(self) -> None:
                raise AssertionError("hostile __post_init__ must never execute")

    assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE


def test_subclass_with_hostile_getattribute_cannot_be_defined() -> None:
    with pytest.raises(TypeError) as excinfo:

        class _HostileAttr(RoughtimeV19RequestSemantics):
            def __getattribute__(self, name: str) -> object:
                raise AssertionError("hostile __getattribute__ must never execute")

    assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE


def test_subclass_with_custom_new_cannot_be_defined() -> None:
    with pytest.raises(TypeError) as excinfo:

        class _CustomNew(RoughtimeV19RequestSemantics):
            def __new__(cls, *args: object, **kwargs: object) -> object:
                raise AssertionError("hostile __new__ must never execute")

    assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE


def test_dynamic_type_subclass_creation_is_rejected() -> None:
    with pytest.raises(TypeError) as excinfo:
        type("_Dynamic", (RoughtimeV19RequestSemantics,), {})
    assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE


def test_seal_error_is_builtin_typeerror_with_fixed_message() -> None:
    with pytest.raises(TypeError) as excinfo:
        type("_Fixed", (RoughtimeV19RequestSemantics,), {})
    assert type(excinfo.value) is TypeError  # exact built-in type, not a semantic error subclass
    assert not isinstance(excinfo.value, RoughtimeV19RequestSemanticError)
    assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE


def test_hostile_subclass_bodies_never_execute() -> None:
    # Every hostile override below raises AssertionError if it is ever called. Sealing at definition time
    # means none of them can run, so the only exception observed is the fixed seal TypeError.
    executed: list[str] = []

    for name, namespace in (
        ("post_init", {"__post_init__": lambda self: executed.append("post_init")}),
        ("getattribute", {"__getattribute__": lambda self, n: executed.append("getattribute")}),
        ("new", {"__new__": lambda cls, *a, **k: executed.append("new")}),
    ):
        with pytest.raises(TypeError) as excinfo:
            type(f"_Hostile_{name}", (RoughtimeV19RequestSemantics,), namespace)
        assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE
    assert executed == []


def test_unbound_post_init_on_foreign_object_is_closed() -> None:
    # Defence in depth: with no subclass definable, the remaining path is calling the base __post_init__
    # unbound against a foreign object. The validator's exact-type gate closes it with the closed reason.
    class _Foreign:
        pass

    foreign = _Foreign()
    request = parse_roughtime_v19_request(_full_packet())
    for attribute in ("versions", "nonce", "message_type", "server_key_id", "padding", "extensions", "raw"):
        object.__setattr__(foreign, attribute, getattr(request, attribute))
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        RoughtimeV19RequestSemantics.__post_init__(foreign)  # type: ignore[arg-type]
    assert _reason(excinfo) is R.ARTIFACT_REQUEST_INCONSISTENT


def test_seal_does_not_add_a_semantic_reason() -> None:
    assert len(R) == 9
    assert not any("subclass" in member.value or "seal" in member.value for member in R)


# =========================================================================================================
# 25. AST / safety matrix
# =========================================================================================================
_PRODUCTION_PATH = (
    Path(__file__).resolve().parents[3] / "src" / "crypto_core" / "validation" / "roughtime_v19_request_semantics.py"
)
_PRODUCTION_SOURCE = _PRODUCTION_PATH.read_text(encoding="utf-8")
_PRODUCTION_TREE = ast.parse(_PRODUCTION_SOURCE)

_ALLOWED_IMPORT_MODULES = {
    "__future__",
    "dataclasses",
    "enum",
    "crypto_core.validation.roughtime_v19_kernel",
}
_FORBIDDEN_IDENTIFIERS = {
    "hashlib",
    "cryptography",
    "nacl",
    "datetime",
    "time",
    "secrets",
    "random",
    "json",
    "pathlib",
    "os",
    "sys",
    "subprocess",
    "threading",
    "socket",
    "requests",
    "urllib",
    "ssl",
}
_FORBIDDEN_CALLS = {"open", "eval", "exec", "compile", "__import__", "input", "globals", "locals", "vars"}


def test_production_imports_are_allowlisted() -> None:
    modules: set[str] = set()
    for node in ast.walk(_PRODUCTION_TREE):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    assert modules <= _ALLOWED_IMPORT_MODULES, modules


def test_production_does_not_import_k2() -> None:
    assert "roughtime_v19_response_semantics" not in _PRODUCTION_SOURCE


def test_production_uses_no_forbidden_identifiers() -> None:
    names: set[str] = set()
    for node in ast.walk(_PRODUCTION_TREE):
        if isinstance(node, ast.Name):
            names.add(node.id)
    assert names.isdisjoint(_FORBIDDEN_IDENTIFIERS), names & _FORBIDDEN_IDENTIFIERS


def test_production_has_no_dangerous_builtin_calls() -> None:
    for node in ast.walk(_PRODUCTION_TREE):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in _FORBIDDEN_CALLS, node.func.id


def test_production_has_no_provider_or_leakage_tokens_in_code() -> None:
    # Provider/crypto/time tokens may appear only inside docstrings (as negations), never as executable
    # identifiers or non-docstring string literals.
    docstrings: set[int] = set()
    module_doc = ast.get_docstring(_PRODUCTION_TREE, clean=False)
    for node in ast.walk(_PRODUCTION_TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(id(doc))
    forbidden_tokens = ("cloudflare", "deribit", "machinetimeanchor", "mt4_verifier", "ed25519", "sha512")
    for node in ast.walk(_PRODUCTION_TREE):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node.value) not in docstrings:
            lowered = node.value.lower()
            for token in forbidden_tokens:
                assert token not in lowered, token
    assert module_doc is not None


# =========================================================================================================
# K1 integration (public contract present; no K1 modification implied)
# =========================================================================================================
def test_builds_on_k1_public_contract() -> None:
    from crypto_core.validation import roughtime_v19_kernel as k1

    assert hasattr(k1, "parse_roughtime_v19_packet")
    assert hasattr(k1, "RoughtimeV19Field")
    request = parse_roughtime_v19_request(_full_packet())
    assert type(request.extensions[0]) is k1.RoughtimeV19Field


def test_k2_response_vers_duplicate_behaviour_is_untouched() -> None:
    # K3 rejects repeated REQUEST VER entries; the merged K2 RESPONSE VERS rule must remain permissive.
    from crypto_core.validation import roughtime_v19_response_semantics as k2

    source = Path(k2.__file__).read_text(encoding="utf-8")
    assert "equal adjacent entries are accepted" in source
    with pytest.raises(RoughtimeV19RequestSemanticError) as excinfo:
        parse_roughtime_v19_request(_packet(versions=[3, 3]))
    assert _reason(excinfo) is R.REQUEST_VER_INVALID
