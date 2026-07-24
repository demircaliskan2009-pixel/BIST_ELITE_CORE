"""Deterministic contract tests for the Roughtime draft-19 bounded RESPONSE semantic decoder (K2).

All fixtures are built by TEST-ONLY encoders (``_encode_message`` / ``_encode_packet``) that are independent
of the production decoder, so positive expectations are never proven by the code under test. Constants
(profile id, tag identities, field lengths, reason inventory) are pinned independently here.

Alignment note (K1 contract): K1 requires every message value except the last (in canonical tag order) to be
four-byte aligned. A non-four-aligned length on a NON-last field is therefore a K1 structural violation and
normalizes to the level ``*_structural_invalid`` reason; the field-specific length reason is proven with a
four-aligned wrong length (which K1 accepts and the semantic layer then rejects) and, for fields that ARE last
at their level (outer INDX, SREP ROOT, DELE MAXT), directly with the non-four-aligned lengths.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from crypto_core.validation.roughtime_v19_kernel import RoughtimeV19Field
from crypto_core.validation.roughtime_v19_response_semantics import (
    ROUGHTIME_V19_RESPONSE_SEMANTIC_PROFILE_ID,
    RoughtimeV19CertificateSemantics,
    RoughtimeV19DelegationSemantics,
    RoughtimeV19ResponseSemanticError,
    RoughtimeV19ResponseSemanticReason,
    RoughtimeV19ResponseSemantics,
    RoughtimeV19SignedResponseSemantics,
    parse_roughtime_v19_response,
)

R = RoughtimeV19ResponseSemanticReason

# --- Independently pinned identity constants --------------------------------------------------------------
_EXPECTED_SEMANTIC_PROFILE_ID = "roughtime-v19-response-semantic-bounded-k2.v1"
_MAGIC = b"ROUGHTIM"

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

_EXT = b"ZZZZ"  # canonical extension tag; largest uint32 so it sorts LAST
_EXT2 = b"YY\x00\x00"  # canonical two-letter extension tag; small uint32 so it sorts EARLY


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


def _encode_packet(message_bytes: bytes, *, magic: bytes = _MAGIC, declared: int | None = None) -> bytes:
    length = len(message_bytes) if declared is None else declared
    return magic + _u32(length) + message_bytes


# --- Default valid field values ---------------------------------------------------------------------------
_OUTER_SIG64 = bytes(range(64))
_NONC32 = bytes(range(32))
_TYPE_OK = _u32(1)
_PATH_EMPTY = b""
_INDX_OK = _u32(0)

_VER_OK = _u32(1)
_RADI_OK = _u32(3)
_MIDP_OK = _u64(150)
_VERS_SECOND = 0x40000001
_VERS_OK = _u32(1) + _u32(_VERS_SECOND)
_ROOT32 = bytes(range(50, 82))

_CERT_SIG64 = bytes(range(100, 164))
_PUBK32 = bytes(range(200, 232))
_MINT_OK = _u64(100)
_MAXT_OK = _u64(200)
_MIDP_VALUE = 150
_MINT_VALUE = 100
_MAXT_VALUE = 200

_DELE_EXT_VAL = b"\xa0\xa1\xa2\xa3"
_CERT_EXT_VAL = b""
_SREP_EXT_VAL = b"\xb0\xb1\xb2\xb3"
_OUTER_EXT_VAL = b"\xc0\xc1\xc2\xc3"


def _ext(tag: bytes, value: bytes) -> RoughtimeV19Field:
    return RoughtimeV19Field(tag=tag, tag_uint32=_le(tag), value=value)


# --- Default pair builders (each accepts overrides, extension list, and a mandatory-tag drop set) ---------
def _dele_pairs(*, pubk=_PUBK32, mint=_MINT_OK, maxt=_MAXT_OK, extra=None, drop=()):
    pairs: list[tuple[bytes, bytes]] = []
    if _TAG_PUBK not in drop:
        pairs.append((_TAG_PUBK, pubk))
    if _TAG_MINT not in drop:
        pairs.append((_TAG_MINT, mint))
    if _TAG_MAXT not in drop:
        pairs.append((_TAG_MAXT, maxt))
    pairs.extend([(_EXT, _DELE_EXT_VAL)] if extra is None else extra)
    return pairs


def _dele_raw(**kwargs) -> bytes:
    return _encode_message(_dele_pairs(**kwargs))


def _cert_pairs(*, sig=_CERT_SIG64, dele=None, extra=None, drop=()):
    if dele is None:
        dele = _dele_raw()
    pairs: list[tuple[bytes, bytes]] = []
    if _TAG_SIG not in drop:
        pairs.append((_TAG_SIG, sig))
    if _TAG_DELE not in drop:
        pairs.append((_TAG_DELE, dele))
    pairs.extend([(_EXT, _CERT_EXT_VAL)] if extra is None else extra)
    return pairs


def _cert_raw(**kwargs) -> bytes:
    return _encode_message(_cert_pairs(**kwargs))


def _srep_pairs(*, ver=_VER_OK, radi=_RADI_OK, midp=_MIDP_OK, vers=_VERS_OK, root=_ROOT32, extra=None, drop=()):
    pairs: list[tuple[bytes, bytes]] = []
    if _TAG_VER not in drop:
        pairs.append((_TAG_VER, ver))
    if _TAG_RADI not in drop:
        pairs.append((_TAG_RADI, radi))
    if _TAG_MIDP not in drop:
        pairs.append((_TAG_MIDP, midp))
    if _TAG_VERS not in drop:
        pairs.append((_TAG_VERS, vers))
    if _TAG_ROOT not in drop:
        pairs.append((_TAG_ROOT, root))
    pairs.extend([(_EXT, _SREP_EXT_VAL)] if extra is None else extra)
    return pairs


def _srep_raw(**kwargs) -> bytes:
    return _encode_message(_srep_pairs(**kwargs))


def _outer_pairs(
    *,
    sig=_OUTER_SIG64,
    nonc=_NONC32,
    type_=_TYPE_OK,
    path=_PATH_EMPTY,
    srep=None,
    cert=None,
    indx=_INDX_OK,
    extra=None,
    drop=(),
):
    if srep is None:
        srep = _srep_raw()
    if cert is None:
        cert = _cert_raw()
    pairs: list[tuple[bytes, bytes]] = []
    if _TAG_SIG not in drop:
        pairs.append((_TAG_SIG, sig))
    if _TAG_NONC not in drop:
        pairs.append((_TAG_NONC, nonc))
    if _TAG_TYPE not in drop:
        pairs.append((_TAG_TYPE, type_))
    if _TAG_PATH not in drop:
        pairs.append((_TAG_PATH, path))
    if _TAG_SREP not in drop:
        pairs.append((_TAG_SREP, srep))
    if _TAG_CERT not in drop:
        pairs.append((_TAG_CERT, cert))
    if _TAG_INDX not in drop:
        pairs.append((_TAG_INDX, indx))
    pairs.extend([(_EXT, _OUTER_EXT_VAL)] if extra is None else extra)
    return pairs


def _packet(**kwargs) -> bytes:
    return _encode_packet(_encode_message(_outer_pairs(**kwargs)))


def _assert_reason(reason: RoughtimeV19ResponseSemanticReason, packet_bytes: object) -> None:
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        parse_roughtime_v19_response(packet_bytes)
    assert excinfo.value.reason is reason


# --- Independent positive artifact builders (constructed WITHOUT the parser) ------------------------------
def _make_delegation() -> RoughtimeV19DelegationSemantics:
    return RoughtimeV19DelegationSemantics(
        pubk=_PUBK32,
        min_time=_MINT_VALUE,
        max_time=_MAXT_VALUE,
        extensions=(_ext(_EXT, _DELE_EXT_VAL),),
        raw=_dele_raw(),
    )


def _make_certificate() -> RoughtimeV19CertificateSemantics:
    return RoughtimeV19CertificateSemantics(
        signature=_CERT_SIG64,
        delegation=_make_delegation(),
        extensions=(_ext(_EXT, _CERT_EXT_VAL),),
        raw=_cert_raw(),
    )


def _make_signed_response() -> RoughtimeV19SignedResponseSemantics:
    return RoughtimeV19SignedResponseSemantics(
        version=1,
        radius_seconds=3,
        midpoint_seconds=_MIDP_VALUE,
        versions=(1, _VERS_SECOND),
        root=_ROOT32,
        extensions=(_ext(_EXT, _SREP_EXT_VAL),),
        raw=_srep_raw(),
    )


def _make_response() -> RoughtimeV19ResponseSemantics:
    return RoughtimeV19ResponseSemantics(
        signature=_OUTER_SIG64,
        nonce=_NONC32,
        message_type=1,
        path=(),
        index=0,
        signed_response=_make_signed_response(),
        certificate=_make_certificate(),
        extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
        raw=_packet(),
    )


# =========================================================================================================
# Profile / identity
# =========================================================================================================
def test_semantic_profile_id_pinned() -> None:
    assert ROUGHTIME_V19_RESPONSE_SEMANTIC_PROFILE_ID == _EXPECTED_SEMANTIC_PROFILE_ID


# =========================================================================================================
# Happy-path matrix
# =========================================================================================================
def test_complete_valid_response_decodes_exactly() -> None:
    packet = _packet()
    response = parse_roughtime_v19_response(packet)

    assert response.raw == packet
    assert response.signature == _OUTER_SIG64
    assert response.nonce == _NONC32
    assert response.message_type == 1
    assert response.path == ()
    assert response.index == 0
    assert len(response.extensions) == 1
    assert response.extensions[0].tag == _EXT
    assert response.extensions[0].value == _OUTER_EXT_VAL

    srep = response.signed_response
    assert srep.raw == _srep_raw()
    assert srep.version == 1
    assert srep.radius_seconds == 3
    assert srep.midpoint_seconds == _MIDP_VALUE
    assert srep.versions == (1, _VERS_SECOND)
    assert srep.root == _ROOT32
    assert len(srep.extensions) == 1 and srep.extensions[0].tag == _EXT

    cert = response.certificate
    assert cert.raw == _cert_raw()
    assert cert.signature == _CERT_SIG64
    assert len(cert.extensions) == 1 and cert.extensions[0].tag == _EXT

    dele = cert.delegation
    assert dele.raw == _dele_raw()
    assert dele.pubk == _PUBK32
    assert dele.min_time == _MINT_VALUE
    assert dele.max_time == _MAXT_VALUE
    assert len(dele.extensions) == 1 and dele.extensions[0].tag == _EXT


def test_exact_raw_bytes_preserved_for_future_signature_verification() -> None:
    packet = _packet()
    response = parse_roughtime_v19_response(packet)
    # Signed bytes are the exact nested values, never reconstructed from decoded fields.
    assert response.raw == packet
    assert response.signed_response.raw == _srep_raw()
    assert response.certificate.raw == _cert_raw()
    assert response.certificate.delegation.raw == _dele_raw()
    assert response.signature == _OUTER_SIG64
    assert response.certificate.signature == _CERT_SIG64


def test_repeated_parse_is_deterministic_and_equal() -> None:
    packet = _packet()
    first = parse_roughtime_v19_response(packet)
    second = parse_roughtime_v19_response(packet)
    assert first == second
    assert hash(first) == hash(second)


def test_parser_and_direct_construction_agree() -> None:
    assert parse_roughtime_v19_response(_packet()) == _make_response()


def test_inclusive_delegation_interval_boundaries_accepted() -> None:
    # MINT == MIDP
    packet_low = _packet(srep=_srep_raw(midp=_u64(100)))
    assert parse_roughtime_v19_response(packet_low).signed_response.midpoint_seconds == 100
    # MIDP == MAXT
    packet_high = _packet(srep=_srep_raw(midp=_u64(200)))
    assert parse_roughtime_v19_response(packet_high).signed_response.midpoint_seconds == 200


def test_zero_node_path_is_valid() -> None:
    assert parse_roughtime_v19_response(_packet(path=b"")).path == ()


def test_maximum_path_nodes_accepted() -> None:
    path = b"".join(bytes([node]) * 32 for node in range(32))
    response = parse_roughtime_v19_response(_packet(path=path))
    assert len(response.path) == 32
    assert response.path[0] == b"\x00" * 32
    assert response.path[31] == bytes([31]) * 32


def test_maximum_versions_entries_accepted() -> None:
    versions = [1, *range(2, 33)]  # 32 strictly ascending entries including selected VER=1
    vers_value = b"".join(_u32(value) for value in versions)
    response = parse_roughtime_v19_response(_packet(srep=_srep_raw(vers=vers_value)))
    assert response.signed_response.versions == tuple(versions)


# =========================================================================================================
# Mandatory-tag matrix (per level, exact level-specific reason)
# =========================================================================================================
@pytest.mark.parametrize("tag", [_TAG_SIG, _TAG_NONC, _TAG_TYPE, _TAG_PATH, _TAG_SREP, _TAG_CERT, _TAG_INDX])
def test_outer_missing_mandatory_tag(tag: bytes) -> None:
    _assert_reason(R.OUTER_MISSING_MANDATORY_TAG, _packet(drop={tag}))


@pytest.mark.parametrize("tag", [_TAG_VER, _TAG_RADI, _TAG_MIDP, _TAG_VERS, _TAG_ROOT])
def test_srep_missing_mandatory_tag(tag: bytes) -> None:
    _assert_reason(R.SREP_MISSING_MANDATORY_TAG, _packet(srep=_srep_raw(drop={tag})))


@pytest.mark.parametrize("tag", [_TAG_SIG, _TAG_DELE])
def test_cert_missing_mandatory_tag(tag: bytes) -> None:
    _assert_reason(R.CERT_MISSING_MANDATORY_TAG, _packet(cert=_cert_raw(drop={tag})))


@pytest.mark.parametrize("tag", [_TAG_PUBK, _TAG_MINT, _TAG_MAXT])
def test_dele_missing_mandatory_tag(tag: bytes) -> None:
    _assert_reason(R.DELE_MISSING_MANDATORY_TAG, _packet(cert=_cert_raw(dele=_dele_raw(drop={tag}))))


# =========================================================================================================
# Known-value matrix — outer
# =========================================================================================================
@pytest.mark.parametrize("length", [60, 68])  # four-aligned wrong lengths reach the semantic SIG check
def test_outer_sig_wrong_four_aligned_length(length: int) -> None:
    _assert_reason(R.OUTER_SIG_INVALID, _packet(sig=bytes(length)))


@pytest.mark.parametrize("length", [63, 65])  # non-four-aligned on a non-last field => K1 structural
def test_outer_sig_non_aligned_length_is_structural(length: int) -> None:
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _packet(sig=bytes(length)))


@pytest.mark.parametrize("length", [28, 36])
def test_outer_nonc_wrong_four_aligned_length(length: int) -> None:
    _assert_reason(R.OUTER_NONC_INVALID, _packet(nonc=bytes(length)))


@pytest.mark.parametrize("length", [31, 33])
def test_outer_nonc_non_aligned_length_is_structural(length: int) -> None:
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _packet(nonc=bytes(length)))


@pytest.mark.parametrize("length", [0, 8])
def test_outer_type_wrong_four_aligned_length(length: int) -> None:
    _assert_reason(R.OUTER_TYPE_INVALID, _packet(type_=bytes(length)))


@pytest.mark.parametrize("length", [3, 5])
def test_outer_type_non_aligned_length_is_structural(length: int) -> None:
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _packet(type_=bytes(length)))


@pytest.mark.parametrize("value", [0, 2, 0xFFFFFFFF])
def test_outer_type_wrong_value(value: int) -> None:
    _assert_reason(R.OUTER_TYPE_INVALID, _packet(type_=_u32(value)))


@pytest.mark.parametrize("path_len", [16, 48])  # four-aligned but not a multiple of 32
def test_outer_path_not_multiple_of_node(path_len: int) -> None:
    _assert_reason(R.OUTER_PATH_INVALID, _packet(path=bytes(path_len)))


def test_outer_path_too_many_nodes() -> None:
    path = b"".join(bytes([node % 256]) * 32 for node in range(33))  # 33 nodes
    _assert_reason(R.OUTER_PATH_INVALID, _packet(path=path))


@pytest.mark.parametrize("length", [3, 5])  # INDX is the LAST outer tag when no extension => reaches check
def test_outer_indx_wrong_length_reaches_field_reason(length: int) -> None:
    _assert_reason(R.OUTER_INDX_INVALID, _packet(indx=bytes(length), extra=[]))


def test_outer_malformed_nested_srep_is_structural() -> None:
    _assert_reason(R.SREP_STRUCTURAL_INVALID, _packet(srep=b"\x00\x00\x00\x00"))


def test_outer_malformed_nested_cert_is_structural() -> None:
    _assert_reason(R.CERT_STRUCTURAL_INVALID, _packet(cert=b"\x00\x00\x00\x00"))


# =========================================================================================================
# Known-value matrix — SREP
# =========================================================================================================
@pytest.mark.parametrize("length", [0, 8])
def test_srep_ver_wrong_length(length: int) -> None:
    _assert_reason(R.SREP_VER_INVALID, _packet(srep=_srep_raw(ver=bytes(length))))


@pytest.mark.parametrize("length", [0, 8])
def test_srep_radi_wrong_length(length: int) -> None:
    _assert_reason(R.SREP_RADI_INVALID, _packet(srep=_srep_raw(radi=bytes(length))))


def test_srep_radi_zero_rejected() -> None:
    _assert_reason(R.SREP_RADI_INVALID, _packet(srep=_srep_raw(radi=_u32(0))))


@pytest.mark.parametrize("length", [4, 12])
def test_srep_midp_wrong_length(length: int) -> None:
    _assert_reason(R.SREP_MIDP_INVALID, _packet(srep=_srep_raw(midp=bytes(length))))


def test_srep_vers_zero_length_rejected() -> None:
    _assert_reason(R.SREP_VERS_INVALID, _packet(srep=_srep_raw(vers=b"")))


def test_srep_vers_non_multiple_of_four_is_structural() -> None:
    # A 6-byte VERS makes the whole SREP message non-four-aligned; SREP is not the last outer tag, so the
    # outer frame's offset alignment is what K1 rejects first -> normalized to OUTER_STRUCTURAL_INVALID.
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _packet(srep=_srep_raw(vers=b"\x01\x00\x00\x00\x02\x00")))


def test_srep_vers_too_many_entries_rejected() -> None:
    vers_value = b"".join(_u32(value) for value in range(1, 34))  # 33 entries
    _assert_reason(R.SREP_VERS_INVALID, _packet(srep=_srep_raw(vers=vers_value)))


def test_srep_vers_descending_rejected() -> None:
    _assert_reason(R.SREP_VERS_INVALID, _packet(srep=_srep_raw(vers=_u32(1) + _u32(0))))


def test_srep_vers_adjacent_duplicate_accepted_and_preserved() -> None:
    # Draft-19 does NOT prohibit repeated response VERS values (only the REQUEST VER list forbids repetition).
    response = parse_roughtime_v19_response(_packet(srep=_srep_raw(ver=_u32(1), vers=_u32(1) + _u32(1))))
    assert response.signed_response.versions == (1, 1)


def test_srep_vers_duplicate_triplet_accepted_and_preserved() -> None:
    response = parse_roughtime_v19_response(_packet(srep=_srep_raw(ver=_u32(1), vers=_u32(1) + _u32(2) + _u32(2))))
    assert response.signed_response.versions == (1, 2, 2)


def test_srep_vers_duplicate_parse_is_deterministic() -> None:
    packet = _packet(srep=_srep_raw(ver=_u32(1), vers=_u32(1) + _u32(1) + _u32(2)))
    first = parse_roughtime_v19_response(packet)
    second = parse_roughtime_v19_response(packet)
    assert first == second
    assert first.signed_response.versions == (1, 1, 2)


def test_srep_selected_version_missing_from_vers_rejected() -> None:
    _assert_reason(R.SREP_VERS_INVALID, _packet(srep=_srep_raw(ver=_u32(9), vers=_u32(1) + _u32(2))))


@pytest.mark.parametrize("length", [28, 36])  # four-aligned wrong lengths keep SREP embeddable, reach check
def test_srep_root_wrong_length_reaches_field_reason(length: int) -> None:
    _assert_reason(R.SREP_ROOT_INVALID, _packet(srep=_srep_raw(root=bytes(length))))


@pytest.mark.parametrize("length", [31, 33])  # non-four-aligned ROOT makes SREP non-embeddable => outer struct
def test_srep_root_non_aligned_length_is_structural(length: int) -> None:
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _packet(srep=_srep_raw(root=bytes(length))))


# =========================================================================================================
# Known-value matrix — CERT
# =========================================================================================================
@pytest.mark.parametrize("length", [60, 68])
def test_cert_sig_wrong_four_aligned_length(length: int) -> None:
    _assert_reason(R.CERT_SIG_INVALID, _packet(cert=_cert_raw(sig=bytes(length))))


@pytest.mark.parametrize("length", [63, 65])  # non-aligned SIG makes CERT non-embeddable => outer structural
def test_cert_sig_non_aligned_length_is_structural(length: int) -> None:
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _packet(cert=_cert_raw(sig=bytes(length))))


def test_cert_malformed_nested_dele_is_structural() -> None:
    _assert_reason(R.DELE_STRUCTURAL_INVALID, _packet(cert=_cert_raw(dele=b"\x00\x00\x00\x00")))


# =========================================================================================================
# Known-value matrix — DELE
# =========================================================================================================
@pytest.mark.parametrize("length", [28, 36])
def test_dele_pubk_wrong_four_aligned_length(length: int) -> None:
    _assert_reason(R.DELE_PUBK_INVALID, _packet(cert=_cert_raw(dele=_dele_raw(pubk=bytes(length)))))


@pytest.mark.parametrize("length", [31, 33])  # non-aligned PUBK makes DELE/CERT non-embeddable => outer struct
def test_dele_pubk_non_aligned_length_is_structural(length: int) -> None:
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _packet(cert=_cert_raw(dele=_dele_raw(pubk=bytes(length)))))


@pytest.mark.parametrize("length", [4, 12])
def test_dele_mint_wrong_length(length: int) -> None:
    _assert_reason(R.DELE_MINT_INVALID, _packet(cert=_cert_raw(dele=_dele_raw(mint=bytes(length)))))


@pytest.mark.parametrize("length", [4, 12])  # four-aligned wrong lengths keep DELE embeddable, reach check
def test_dele_maxt_wrong_length_reaches_field_reason(length: int) -> None:
    _assert_reason(R.DELE_MAXT_INVALID, _packet(cert=_cert_raw(dele=_dele_raw(maxt=bytes(length)))))


@pytest.mark.parametrize("length", [7, 9])  # non-aligned MAXT makes DELE/CERT non-embeddable => outer struct
def test_dele_maxt_non_aligned_length_is_structural(length: int) -> None:
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _packet(cert=_cert_raw(dele=_dele_raw(maxt=bytes(length)))))


def test_dele_interval_invalid_min_greater_than_max() -> None:
    _assert_reason(R.DELE_INTERVAL_INVALID, _packet(cert=_cert_raw(dele=_dele_raw(mint=_u64(300), maxt=_u64(200)))))


def test_midpoint_below_delegation_interval() -> None:
    _assert_reason(R.MIDPOINT_OUTSIDE_DELEGATION_INTERVAL, _packet(srep=_srep_raw(midp=_u64(50))))


def test_midpoint_above_delegation_interval() -> None:
    _assert_reason(R.MIDPOINT_OUTSIDE_DELEGATION_INTERVAL, _packet(srep=_srep_raw(midp=_u64(250))))


# =========================================================================================================
# Grease / extension matrix — undefined tags accepted and preserved, never a rejection reason
# =========================================================================================================
def test_extension_preserved_at_every_level_simultaneously() -> None:
    response = parse_roughtime_v19_response(_packet())
    assert response.extensions[0].tag == _EXT
    assert response.signed_response.extensions[0].tag == _EXT
    assert response.certificate.extensions[0].tag == _EXT
    assert response.certificate.delegation.extensions[0].tag == _EXT


def test_no_extensions_is_valid() -> None:
    response = parse_roughtime_v19_response(
        _packet(extra=[], srep=_srep_raw(extra=[]), cert=_cert_raw(dele=_dele_raw(extra=[]), extra=[]))
    )
    assert response.extensions == ()
    assert response.signed_response.extensions == ()
    assert response.certificate.extensions == ()
    assert response.certificate.delegation.extensions == ()


@pytest.mark.parametrize("value", [b"", b"\x00\x00\x00\x00", b"\xde\xad\xbe\xef\xde\xad\xbe\xef"])
def test_outer_extension_arbitrary_values_preserved(value: bytes) -> None:
    response = parse_roughtime_v19_response(_packet(extra=[(_EXT, value)]))
    assert len(response.extensions) == 1
    assert response.extensions[0].tag == _EXT
    assert response.extensions[0].value == value


def test_one_letter_and_four_letter_extension_tags_preserved() -> None:
    one_letter = b"A\x00\x00\x00"
    four_letter = b"WXYZ"
    response = parse_roughtime_v19_response(
        _packet(extra=[(one_letter, b"\x01\x02\x03\x04"), (four_letter, b"\x05\x06\x07\x08")])
    )
    tags = {field.tag for field in response.extensions}
    assert tags == {one_letter, four_letter}


def test_multiple_extensions_preserved_in_canonical_order() -> None:
    # _EXT2 (small uint32) sorts before mandatory tags; _EXT (large) sorts last. Canonical order is ascending.
    response = parse_roughtime_v19_response(_packet(extra=[(_EXT, _OUTER_EXT_VAL), (_EXT2, b"\x09\x09\x09\x09")]))
    ext_tags = [field.tag for field in response.extensions]
    assert ext_tags == sorted(ext_tags, key=_le)
    assert set(ext_tags) == {_EXT, _EXT2}


def test_srep_extension_preserved() -> None:
    response = parse_roughtime_v19_response(_packet(srep=_srep_raw(extra=[(_EXT, b"\x11\x22\x33\x44")])))
    assert response.signed_response.extensions[0].value == b"\x11\x22\x33\x44"


def test_cert_extension_preserved() -> None:
    response = parse_roughtime_v19_response(_packet(cert=_cert_raw(extra=[(_EXT, b"\x55\x66\x77\x88")])))
    assert response.certificate.extensions[0].value == b"\x55\x66\x77\x88"


def test_dele_extension_preserved() -> None:
    response = parse_roughtime_v19_response(
        _packet(cert=_cert_raw(dele=_dele_raw(extra=[(_EXT, b"\x99\xaa\xbb\xcc")])))
    )
    assert response.certificate.delegation.extensions[0].value == b"\x99\xaa\xbb\xcc"


# =========================================================================================================
# Trust-boundary matrix — exact public input types
# =========================================================================================================
class _BytesSubclass(bytes):
    pass


class _ByteArraySource:
    pass


class _TupleSubclass(tuple):
    pass


class _IntSubclass(int):
    pass


class _FieldSubclass(RoughtimeV19Field):
    pass


class _DelegationSubclass(RoughtimeV19DelegationSemantics):
    pass


class _CertificateSubclass(RoughtimeV19CertificateSemantics):
    pass


class _SignedResponseSubclass(RoughtimeV19SignedResponseSemantics):
    pass


class _ResponseSubclass(RoughtimeV19ResponseSemantics):
    pass


class _HostileEqBytes(bytes):
    def __eq__(self, other: object) -> bool:  # pragma: no cover - must never be reached before the type gate
        raise AssertionError("equality touched before exact-type validation")

    __hash__ = bytes.__hash__


def test_parser_rejects_bytes_subclass() -> None:
    _assert_reason(R.WRONG_INPUT_TYPE, _BytesSubclass(_packet()))


def test_parser_rejects_bytearray() -> None:
    _assert_reason(R.WRONG_INPUT_TYPE, bytearray(_packet()))


def test_parser_rejects_memoryview() -> None:
    _assert_reason(R.WRONG_INPUT_TYPE, memoryview(_packet()))


def test_parser_rejects_hostile_equality_bytes_before_use() -> None:
    _assert_reason(R.WRONG_INPUT_TYPE, _HostileEqBytes(_packet()))


@pytest.mark.parametrize(
    "raw",
    [_dele_raw(), _cert_raw(), _srep_raw(), _packet()],
)
def test_artifact_raw_bytes_subclass_rejected(raw: bytes) -> None:
    # Each artifact rejects a bytes-subclass raw (value-correct) via its exact-type gate.
    with pytest.raises(RoughtimeV19ResponseSemanticError):
        RoughtimeV19DelegationSemantics(
            pubk=_PUBK32,
            min_time=_MINT_VALUE,
            max_time=_MAXT_VALUE,
            extensions=(_ext(_EXT, _DELE_EXT_VAL),),
            raw=_BytesSubclass(_dele_raw()),
        )


def test_delegation_bytes_subclass_pubk_rejected() -> None:
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19DelegationSemantics(
            pubk=_BytesSubclass(_PUBK32),
            min_time=_MINT_VALUE,
            max_time=_MAXT_VALUE,
            extensions=(_ext(_EXT, _DELE_EXT_VAL),),
            raw=_dele_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_delegation_int_subclass_min_time_rejected() -> None:
    subclass_value = _IntSubclass(_MINT_VALUE)
    assert subclass_value == _MINT_VALUE  # value-correct: fails only on the exact-type gate
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19DelegationSemantics(
            pubk=_PUBK32,
            min_time=subclass_value,
            max_time=_MAXT_VALUE,
            extensions=(_ext(_EXT, _DELE_EXT_VAL),),
            raw=_dele_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_delegation_bool_max_time_rejected() -> None:
    # max_time decoded value cannot be a bool; a bool is not an exact int.
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19DelegationSemantics(
            pubk=_PUBK32,
            min_time=_MINT_VALUE,
            max_time=True,
            extensions=(_ext(_EXT, _DELE_EXT_VAL),),
            raw=_dele_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_response_bool_index_rejected() -> None:
    # index decoded value is 0; False == 0 but bool is not an exact int (causally isolated to the type gate).
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(),
            index=False,
            signed_response=_make_signed_response(),
            certificate=_make_certificate(),
            extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
            raw=_packet(),
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


def test_signed_response_int_subclass_version_entry_rejected() -> None:
    versions = (_IntSubclass(1), _VERS_SECOND)
    assert versions[0] == 1
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19SignedResponseSemantics(
            version=1,
            radius_seconds=3,
            midpoint_seconds=_MIDP_VALUE,
            versions=versions,
            root=_ROOT32,
            extensions=(_ext(_EXT, _SREP_EXT_VAL),),
            raw=_srep_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_SREP_INCONSISTENT


def test_delegation_tuple_subclass_extensions_rejected() -> None:
    good = _ext(_EXT, _DELE_EXT_VAL)
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19DelegationSemantics(
            pubk=_PUBK32,
            min_time=_MINT_VALUE,
            max_time=_MAXT_VALUE,
            extensions=_TupleSubclass((good,)),
            raw=_dele_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_delegation_field_subclass_extension_rejected() -> None:
    forged = _FieldSubclass(tag=_EXT, tag_uint32=_le(_EXT), value=_DELE_EXT_VAL)  # value-correct subclass
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19DelegationSemantics(
            pubk=_PUBK32,
            min_time=_MINT_VALUE,
            max_time=_MAXT_VALUE,
            extensions=(forged,),
            raw=_dele_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_response_signed_response_subclass_rejected() -> None:
    subclass = _SignedResponseSubclass(
        version=1,
        radius_seconds=3,
        midpoint_seconds=_MIDP_VALUE,
        versions=(1, _VERS_SECOND),
        root=_ROOT32,
        extensions=(_ext(_EXT, _SREP_EXT_VAL),),
        raw=_srep_raw(),
    )
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(),
            index=0,
            signed_response=subclass,
            certificate=_make_certificate(),
            extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
            raw=_packet(),
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


def test_response_certificate_subclass_rejected() -> None:
    subclass = _CertificateSubclass(
        signature=_CERT_SIG64,
        delegation=_make_delegation(),
        extensions=(_ext(_EXT, _CERT_EXT_VAL),),
        raw=_cert_raw(),
    )
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(),
            index=0,
            signed_response=_make_signed_response(),
            certificate=subclass,
            extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
            raw=_packet(),
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


def test_certificate_delegation_subclass_rejected() -> None:
    subclass = _DelegationSubclass(
        pubk=_PUBK32,
        min_time=_MINT_VALUE,
        max_time=_MAXT_VALUE,
        extensions=(_ext(_EXT, _DELE_EXT_VAL),),
        raw=_dele_raw(),
    )
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19CertificateSemantics(
            signature=_CERT_SIG64,
            delegation=subclass,
            extensions=(_ext(_EXT, _CERT_EXT_VAL),),
            raw=_cert_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_CERT_INCONSISTENT


def test_response_path_node_bytes_subclass_rejected() -> None:
    packet = _packet(path=b"\x07" * 32)
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(_BytesSubclass(b"\x07" * 32),),
            index=0,
            signed_response=_make_signed_response(),
            certificate=_make_certificate(),
            extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
            raw=packet,
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


# =========================================================================================================
# Artifact self-validation matrix — forgery / mutation / immutability
# =========================================================================================================
def test_independent_positive_artifact_construction() -> None:
    dele = _make_delegation()
    cert = _make_certificate()
    srep = _make_signed_response()
    response = _make_response()
    assert dele.raw == _dele_raw()
    assert cert.delegation == dele
    assert srep.version == 1
    assert response.signed_response == srep
    assert response.certificate == cert


def test_delegation_scalar_mutation_rejected() -> None:
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19DelegationSemantics(
            pubk=_PUBK32,
            min_time=_MINT_VALUE + 1,
            max_time=_MAXT_VALUE,
            extensions=(_ext(_EXT, _DELE_EXT_VAL),),
            raw=_dele_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_delegation_raw_substitution_rejected() -> None:
    other_raw = _dele_raw(pubk=bytes(range(1, 33)))
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19DelegationSemantics(
            pubk=_PUBK32,
            min_time=_MINT_VALUE,
            max_time=_MAXT_VALUE,
            extensions=(_ext(_EXT, _DELE_EXT_VAL),),
            raw=other_raw,
        )
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_delegation_malformed_raw_rejected() -> None:
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19DelegationSemantics(
            pubk=_PUBK32,
            min_time=_MINT_VALUE,
            max_time=_MAXT_VALUE,
            extensions=(_ext(_EXT, _DELE_EXT_VAL),),
            raw=b"\x00\x00\x00\x00",
        )
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_delegation_extension_removed_rejected() -> None:
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19DelegationSemantics(
            pubk=_PUBK32,
            min_time=_MINT_VALUE,
            max_time=_MAXT_VALUE,
            extensions=(),
            raw=_dele_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_delegation_extension_value_forged_rejected() -> None:
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19DelegationSemantics(
            pubk=_PUBK32,
            min_time=_MINT_VALUE,
            max_time=_MAXT_VALUE,
            extensions=(_ext(_EXT, b"\x00\x00\x00\x00"),),
            raw=_dele_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_delegation_extension_reordered_rejected() -> None:
    raw = _dele_raw(extra=[(_EXT, _DELE_EXT_VAL), (_EXT2, b"\x01\x02\x03\x04")])
    correct = parse_roughtime_v19_response(_packet(cert=_cert_raw(dele=raw))).certificate.delegation.extensions
    reordered = (correct[1], correct[0])
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19DelegationSemantics(
            pubk=_PUBK32,
            min_time=_MINT_VALUE,
            max_time=_MAXT_VALUE,
            extensions=reordered,
            raw=raw,
        )
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_signed_response_versions_mutation_rejected() -> None:
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19SignedResponseSemantics(
            version=1,
            radius_seconds=3,
            midpoint_seconds=_MIDP_VALUE,
            versions=(1, _VERS_SECOND + 1),
            root=_ROOT32,
            extensions=(_ext(_EXT, _SREP_EXT_VAL),),
            raw=_srep_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_SREP_INCONSISTENT


def test_signed_response_root_mutation_rejected() -> None:
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19SignedResponseSemantics(
            version=1,
            radius_seconds=3,
            midpoint_seconds=_MIDP_VALUE,
            versions=(1, _VERS_SECOND),
            root=bytes(range(1, 33)),
            extensions=(_ext(_EXT, _SREP_EXT_VAL),),
            raw=_srep_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_SREP_INCONSISTENT


def test_certificate_nested_delegation_substitution_rejected() -> None:
    # A valid but different delegation whose raw does not match the DELE embedded in cert_raw.
    other_delegation = RoughtimeV19DelegationSemantics(
        pubk=bytes(range(1, 33)),
        min_time=_MINT_VALUE,
        max_time=_MAXT_VALUE,
        extensions=(_ext(_EXT, _DELE_EXT_VAL),),
        raw=_dele_raw(pubk=bytes(range(1, 33))),
    )
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19CertificateSemantics(
            signature=_CERT_SIG64,
            delegation=other_delegation,
            extensions=(_ext(_EXT, _CERT_EXT_VAL),),
            raw=_cert_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_CERT_INCONSISTENT


def test_response_nested_srep_substitution_rejected() -> None:
    other_srep = RoughtimeV19SignedResponseSemantics(
        version=1,
        radius_seconds=9,
        midpoint_seconds=_MIDP_VALUE,
        versions=(1, _VERS_SECOND),
        root=_ROOT32,
        extensions=(_ext(_EXT, _SREP_EXT_VAL),),
        raw=_srep_raw(radi=_u32(9)),
    )
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(),
            index=0,
            signed_response=other_srep,
            certificate=_make_certificate(),
            extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
            raw=_packet(),
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


@pytest.mark.parametrize("attribute", ["pubk", "min_time", "max_time", "extensions", "raw"])
def test_delegation_is_frozen_against_assignment_and_deletion(attribute: str) -> None:
    dele = _make_delegation()
    with pytest.raises(Exception):
        setattr(dele, attribute, getattr(dele, attribute))
    with pytest.raises(Exception):
        delattr(dele, attribute)


def test_response_frozen_and_nested_stable() -> None:
    response = _make_response()
    with pytest.raises(Exception):
        response.raw = _packet()  # type: ignore[misc]
    # Nested artifacts remain unchanged and consistent after a rejected assignment.
    assert response.signed_response.raw == _srep_raw()
    assert response.certificate.delegation.raw == _dele_raw()


# =========================================================================================================
# Complete nested-state binding matrix (exact-type objects built without / mutated after their initializer)
# =========================================================================================================
def _hollow(cls: type, **attrs: object) -> object:
    """An exact-type instance built WITHOUT its dataclass initializer (object.__new__), attributes set raw."""
    obj = object.__new__(cls)
    for name, value in attrs.items():
        object.__setattr__(obj, name, value)
    return obj


def _mutate(obj: object, **attrs: object) -> object:
    """Replace fields on an already-constructed frozen artifact via low-level direct state replacement."""
    for name, value in attrs.items():
        object.__setattr__(obj, name, value)
    return obj


# --- A. Signed-response parent boundary ---
def test_hollow_signed_response_raw_only_rejected_by_response_parent() -> None:
    hollow = _hollow(RoughtimeV19SignedResponseSemantics, raw=_srep_raw())  # matching raw, no semantic fields
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(),
            index=0,
            signed_response=hollow,
            certificate=_make_certificate(),
            extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
            raw=_packet(),
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


def test_signed_response_all_fields_present_one_wrong_rejected() -> None:
    hollow = _hollow(
        RoughtimeV19SignedResponseSemantics,
        version=1,
        radius_seconds=3,
        midpoint_seconds=151,  # 151 != 150
        versions=(1, _VERS_SECOND),
        root=_ROOT32,
        extensions=(_ext(_EXT, _SREP_EXT_VAL),),
        raw=_srep_raw(),
    )
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(),
            index=0,
            signed_response=hollow,
            certificate=_make_certificate(),
            extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
            raw=_packet(),
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


# --- B. Certificate parent boundary ---
def test_hollow_certificate_raw_only_rejected_by_response_parent() -> None:
    hollow = _hollow(RoughtimeV19CertificateSemantics, raw=_cert_raw())
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(),
            index=0,
            signed_response=_make_signed_response(),
            certificate=hollow,
            extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
            raw=_packet(),
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


def test_certificate_inconsistent_signature_rejected_by_response_parent() -> None:
    hollow = _hollow(
        RoughtimeV19CertificateSemantics,
        signature=bytes(range(1, 65)),  # wrong signature
        delegation=_make_delegation(),
        extensions=(_ext(_EXT, _CERT_EXT_VAL),),
        raw=_cert_raw(),
    )
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(),
            index=0,
            signed_response=_make_signed_response(),
            certificate=hollow,
            extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
            raw=_packet(),
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


# --- C. Delegation boundary (certificate parent) ---
def test_hollow_delegation_raw_only_rejected_by_certificate_parent() -> None:
    hollow = _hollow(RoughtimeV19DelegationSemantics, raw=_dele_raw())
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19CertificateSemantics(
            signature=_CERT_SIG64,
            delegation=hollow,
            extensions=(_ext(_EXT, _CERT_EXT_VAL),),
            raw=_cert_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_CERT_INCONSISTENT


def test_delegation_inconsistent_pubk_rejected_by_certificate_parent() -> None:
    hollow = _hollow(
        RoughtimeV19DelegationSemantics,
        pubk=bytes(range(1, 33)),  # wrong pubk
        min_time=_MINT_VALUE,
        max_time=_MAXT_VALUE,
        extensions=(_ext(_EXT, _DELE_EXT_VAL),),
        raw=_dele_raw(),
    )
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19CertificateSemantics(
            signature=_CERT_SIG64,
            delegation=hollow,
            extensions=(_ext(_EXT, _CERT_EXT_VAL),),
            raw=_cert_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_CERT_INCONSISTENT


# --- D. Existing valid object mutated before parent admission ---
def test_mutated_signed_response_rejected_by_response_parent() -> None:
    srep = _mutate(_make_signed_response(), midpoint_seconds=149)  # raw unchanged, midpoint now wrong
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(),
            index=0,
            signed_response=srep,
            certificate=_make_certificate(),
            extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
            raw=_packet(),
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


def test_mutated_certificate_rejected_by_response_parent() -> None:
    cert = _mutate(_make_certificate(), signature=bytes(range(1, 65)))  # raw unchanged, signature now wrong
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(),
            index=0,
            signed_response=_make_signed_response(),
            certificate=cert,
            extensions=(_ext(_EXT, _OUTER_EXT_VAL),),
            raw=_packet(),
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


def test_mutated_delegation_rejected_by_certificate_parent() -> None:
    dele = _mutate(_make_delegation(), min_time=_MINT_VALUE + 1)  # raw unchanged, min_time now wrong
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19CertificateSemantics(
            signature=_CERT_SIG64,
            delegation=dele,
            extensions=(_ext(_EXT, _CERT_EXT_VAL),),
            raw=_cert_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_CERT_INCONSISTENT


# --- E. Extension boundary — exact-type K1 field built without/with malformed internal state ---
def _hollow_field(**attrs: object) -> RoughtimeV19Field:
    return _hollow(RoughtimeV19Field, **attrs)  # type: ignore[return-value]


def _dele_with_extensions(extensions: tuple[object, ...]) -> None:
    RoughtimeV19DelegationSemantics(
        pubk=_PUBK32,
        min_time=_MINT_VALUE,
        max_time=_MAXT_VALUE,
        extensions=extensions,
        raw=_dele_raw(),
    )


@pytest.mark.parametrize(
    "field",
    [
        _hollow_field(),  # no attributes at all
        _hollow_field(tag=_EXT, tag_uint32=_le(_EXT)),  # missing value attribute
        _hollow_field(tag=_EXT, tag_uint32=999, value=_DELE_EXT_VAL),  # exact tag, wrong numeric value
        _hollow_field(tag=_BytesSubclass(_EXT), tag_uint32=_le(_EXT), value=_DELE_EXT_VAL),  # bytes-subclass tag
        _hollow_field(tag=_EXT, tag_uint32=_IntSubclass(_le(_EXT)), value=_DELE_EXT_VAL),  # int-subclass uint32
        _hollow_field(
            tag=b"\x01\x02\x03\x04", tag_uint32=_le(b"\x01\x02\x03\x04"), value=_DELE_EXT_VAL
        ),  # non-canonical
        _hollow_field(tag=_EXT, tag_uint32=_le(_EXT), value=b"\x00\x00\x00\x00"),  # value-correct type, wrong value
        _hollow_field(tag=_EXT, tag_uint32=_le(_EXT), value=_HostileEqBytes(_DELE_EXT_VAL)),  # hostile-eq value
    ],
)
def test_incomplete_extension_field_rejected_in_delegation(field: RoughtimeV19Field) -> None:
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        _dele_with_extensions((field,))
    assert excinfo.value.reason is R.ARTIFACT_DELE_INCONSISTENT


def test_incomplete_extension_field_rejected_in_signed_response() -> None:
    hollow_field = _hollow_field()  # no attributes -> must not leak AttributeError
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19SignedResponseSemantics(
            version=1,
            radius_seconds=3,
            midpoint_seconds=_MIDP_VALUE,
            versions=(1, _VERS_SECOND),
            root=_ROOT32,
            extensions=(hollow_field,),
            raw=_srep_raw(),
        )
    assert excinfo.value.reason is R.ARTIFACT_SREP_INCONSISTENT


def test_incomplete_extension_field_rejected_in_outer_response() -> None:
    hollow_field = _hollow_field(tag=_EXT, tag_uint32=999, value=_OUTER_EXT_VAL)  # wrong numeric value
    with pytest.raises(RoughtimeV19ResponseSemanticError) as excinfo:
        RoughtimeV19ResponseSemantics(
            signature=_OUTER_SIG64,
            nonce=_NONC32,
            message_type=1,
            path=(),
            index=0,
            signed_response=_make_signed_response(),
            certificate=_make_certificate(),
            extensions=(hollow_field,),
            raw=_packet(),
        )
    assert excinfo.value.reason is R.ARTIFACT_RESPONSE_INCONSISTENT


def test_incomplete_extension_field_does_not_leak_raw_exception() -> None:
    # A field with no internal state at all must surface the closed reason, never a raw AttributeError.
    try:
        _dele_with_extensions((_hollow_field(),))
    except RoughtimeV19ResponseSemanticError:
        pass
    except Exception as exc:  # noqa: BLE001 - the whole point is proving nothing else escapes
        raise AssertionError(f"raw exception leaked: {type(exc).__name__}") from exc
    else:  # pragma: no cover
        raise AssertionError("expected a closed semantic error")


# --- F. Positive independence after complete-state validation ---
def test_full_valid_nested_hierarchy_still_accepted() -> None:
    response = _make_response()  # independently constructed nested hierarchy
    assert response == parse_roughtime_v19_response(_packet())
    assert response.certificate.delegation.min_time == _MINT_VALUE
    assert response.signed_response.versions == (1, _VERS_SECOND)


# =========================================================================================================
# K1 normalization matrix
# =========================================================================================================
def test_wrong_packet_magic_normalized_to_outer_structural() -> None:
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _encode_packet(_encode_message(_outer_pairs()), magic=b"XXXXXXXX"))


def test_declared_length_mismatch_normalized_to_outer_structural() -> None:
    message = _encode_message(_outer_pairs())
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _encode_packet(message, declared=len(message) + 4))


def test_malformed_top_level_message_normalized_to_outer_structural() -> None:
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _encode_packet(b"\x00\x00\x00\x00"))


def test_k1_profile_limit_normalized_to_outer_structural_not_malformed() -> None:
    # A packet above the inherited K1 bounded-profile ceiling is OUTSIDE the profile, not malformed draft-19.
    oversize_extension = b"\x00" * 5000
    _assert_reason(R.OUTER_STRUCTURAL_INVALID, _packet(extra=[(_EXT, oversize_extension)]))


def test_no_raw_kernel_error_leaks() -> None:
    # Every structural failure surfaces as the closed semantic error type, never a raw kernel error.
    try:
        parse_roughtime_v19_response(_encode_packet(b"\x00\x00\x00\x00"))
    except RoughtimeV19ResponseSemanticError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected a semantic error")


# =========================================================================================================
# Error contract matrix
# =========================================================================================================
_EXPECTED_REASON_MAPPING = {
    "WRONG_INPUT_TYPE": "wrong_input_type",
    "OUTER_STRUCTURAL_INVALID": "outer_structural_invalid",
    "OUTER_MISSING_MANDATORY_TAG": "outer_missing_mandatory_tag",
    "OUTER_SIG_INVALID": "outer_sig_invalid",
    "OUTER_NONC_INVALID": "outer_nonc_invalid",
    "OUTER_TYPE_INVALID": "outer_type_invalid",
    "OUTER_PATH_INVALID": "outer_path_invalid",
    "OUTER_INDX_INVALID": "outer_indx_invalid",
    "SREP_STRUCTURAL_INVALID": "srep_structural_invalid",
    "SREP_MISSING_MANDATORY_TAG": "srep_missing_mandatory_tag",
    "SREP_VER_INVALID": "srep_ver_invalid",
    "SREP_RADI_INVALID": "srep_radi_invalid",
    "SREP_MIDP_INVALID": "srep_midp_invalid",
    "SREP_VERS_INVALID": "srep_vers_invalid",
    "SREP_ROOT_INVALID": "srep_root_invalid",
    "CERT_STRUCTURAL_INVALID": "cert_structural_invalid",
    "CERT_MISSING_MANDATORY_TAG": "cert_missing_mandatory_tag",
    "CERT_SIG_INVALID": "cert_sig_invalid",
    "DELE_STRUCTURAL_INVALID": "dele_structural_invalid",
    "DELE_MISSING_MANDATORY_TAG": "dele_missing_mandatory_tag",
    "DELE_PUBK_INVALID": "dele_pubk_invalid",
    "DELE_MINT_INVALID": "dele_mint_invalid",
    "DELE_MAXT_INVALID": "dele_maxt_invalid",
    "DELE_INTERVAL_INVALID": "dele_interval_invalid",
    "MIDPOINT_OUTSIDE_DELEGATION_INTERVAL": "midpoint_outside_delegation_interval",
    "ARTIFACT_DELE_INCONSISTENT": "artifact_dele_inconsistent",
    "ARTIFACT_CERT_INCONSISTENT": "artifact_cert_inconsistent",
    "ARTIFACT_SREP_INCONSISTENT": "artifact_srep_inconsistent",
    "ARTIFACT_RESPONSE_INCONSISTENT": "artifact_response_inconsistent",
}


def test_reason_inventory_exact_count() -> None:
    assert len(list(RoughtimeV19ResponseSemanticReason)) == 29
    assert len(_EXPECTED_REASON_MAPPING) == 29


def test_reason_name_value_mapping_pinned() -> None:
    actual = {member.name: member.value for member in RoughtimeV19ResponseSemanticReason}
    assert actual == _EXPECTED_REASON_MAPPING


def test_error_requires_exact_reason_member() -> None:
    with pytest.raises(TypeError):
        RoughtimeV19ResponseSemanticError("wrong_input_type")  # type: ignore[arg-type]


def test_error_rejects_hostile_value_property_before_read() -> None:
    class _HostileReason:
        @property
        def value(self) -> str:  # pragma: no cover - must never be read
            raise AssertionError("value property touched")

    with pytest.raises(TypeError):
        RoughtimeV19ResponseSemanticError(_HostileReason())  # type: ignore[arg-type]


def test_error_str_is_reason_value() -> None:
    error = RoughtimeV19ResponseSemanticError(R.OUTER_SIG_INVALID)
    assert str(error) == "outer_sig_invalid"
    assert error.reason is R.OUTER_SIG_INVALID
    assert error.args == ("outer_sig_invalid",)


@pytest.mark.parametrize("attribute", ["reason", "_reason", "args"])
def test_error_is_immutable(attribute: str) -> None:
    error = RoughtimeV19ResponseSemanticError(R.DELE_MINT_INVALID)
    with pytest.raises(AttributeError):
        setattr(error, attribute, R.DELE_MAXT_INVALID)
    with pytest.raises(AttributeError):
        delattr(error, attribute)
    assert error.reason is R.DELE_MINT_INVALID
    assert str(error) == "dele_mint_invalid"


# =========================================================================================================
# AST / safety matrix
# =========================================================================================================
_PRODUCTION_PATH = (
    Path(__file__).resolve().parents[3] / "src" / "crypto_core" / "validation" / "roughtime_v19_response_semantics.py"
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
    "requests",
    "urllib",
    "socket",
    "pathlib",
    "os",
    "sys",
    "subprocess",
    "threading",
    "random",
    "secrets",
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
    # Provider/crypto/time tokens may appear only inside the module or function docstrings (as negations),
    # never as executable identifiers or non-docstring string literals.
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
    assert module_doc is not None  # the module keeps its honest-scope docstring


# =========================================================================================================
# K1 integration (public contract present; no K1 modification implied)
# =========================================================================================================
def test_builds_on_k1_public_contract() -> None:
    from crypto_core.validation import roughtime_v19_kernel as k1

    assert hasattr(k1, "parse_roughtime_v19_message")
    assert hasattr(k1, "parse_roughtime_v19_packet")
    assert hasattr(k1, "RoughtimeV19Field")
    # A K2 extension field is exactly a K1 field object.
    response = parse_roughtime_v19_response(_packet())
    assert type(response.extensions[0]) is k1.RoughtimeV19Field
