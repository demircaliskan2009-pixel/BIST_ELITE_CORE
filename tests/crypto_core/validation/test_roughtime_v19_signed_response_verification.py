"""Deterministic contract tests for the Roughtime draft-19 SREP/signed-response verifier (K5-SREP).

Vector provenance: every cryptographic vector below is copied verbatim from the accepted Class-C research
packet (MT4_RT19_SIGNATURE_VECTOR_ADMISSION_PASS, corpus V01-V25, raw SHA-256
c877e0970524adc73e248ac0616eda666db6ea0bcafa85bfd0cca7c5dbbfafbb, canonical-LF SHA-256
d530414138efb0b5a7c330c140e67b670fddf675b48a6469c66a4579aa7d89e8). Nothing is generated here, nothing is
paraphrased and no hex is elided. The SREP-relevant records are V05 (positive, cryptography/OpenSSL
generator), V06 (wrong context), V07 (missing trailing NUL), V08 (re-encoded SREP; PyNaCl/libsodium
generator, so its exact-SREP transcript is the REVERSE-backend positive), V10 (wrong delegated key), V12
(one-bit SREP mutation) and V20-V25 (interval variants, all SIGNATURE_VALID). Key-policy records V13/V14/
V15/V16/V17/V18/V19 are reused for the shared Ed25519 encoding policy. `cryptography` is NOT a runtime or
test dependency and is never imported.

Small-order inventory provenance: the seven encodings are transcribed byte-for-byte from the immutable
vendored libsodium source of the pinned backend - pyca/pynacl tag 1.6.2,
src/libsodium/src/libsodium/crypto_core/ed25519/ref10/ed25519_ref10.c, function ge25519_has_small_order,
static table blacklist[][32], whose own COMPILER_ASSERT fixes the count at exactly seven. They are pinned
here independently of the production module so the module cannot prove its own inventory.

Response fixtures are built by TEST-ONLY encoders that never call a production encoder; they embed the
packet's exact SREP, CERT and DELE bytes verbatim so K2 preserves them unchanged.
"""

from __future__ import annotations

import ast
import copy
import gc
import operator
import pickle
import weakref
from pathlib import Path

import pytest

from crypto_core.validation.roughtime_v19_certificate_verification import (
    RoughtimeV19CertificateVerification,
    verify_roughtime_v19_certificate,
)
from crypto_core.validation.roughtime_v19_response_semantics import (
    RoughtimeV19ResponseSemantics,
    parse_roughtime_v19_response,
)
from crypto_core.validation.roughtime_v19_signed_response_verification import (
    ROUGHTIME_V19_SIGNED_RESPONSE_VERIFICATION_PROFILE_ID,
    RoughtimeV19SignedResponseVerification,
    RoughtimeV19SignedResponseVerificationError,
    RoughtimeV19SignedResponseVerificationReason,
    verify_roughtime_v19_signed_response,
)

R = RoughtimeV19SignedResponseVerificationReason

# --- Independently pinned identity constants --------------------------------------------------------------
_EXPECTED_PROFILE_ID = "roughtime-v19-signed-response-verification-bounded-k5-srep.v1"
_EXPECTED_SEAL_MESSAGE = "RoughtimeV19SignedResponseVerification is a sealed artifact type and cannot be subclassed"
_EXPECTED_REASON_TYPE_MESSAGE = (
    "RoughtimeV19SignedResponseVerificationError requires a RoughtimeV19SignedResponseVerificationReason member"
)
_EXPECTED_REASON_VALUES = (
    "wrong_input_type",
    "input_artifact_inconsistent",
    "delegated_public_key_invalid",
    "srep_signature_invalid",
    "crypto_backend_failure",
    "artifact_signed_response_verification_inconsistent",
)
_EXPECTED_ARTIFACT_FIELDS = (
    "response_raw",
    "long_term_public_key",
    "delegated_public_key",
    "signed_response_raw",
    "response_signature",
    "signed_root",
    "signed_midpoint",
    "signed_radius",
    "signed_version",
    "signed_versions",
)
_FORBIDDEN_FIELD_TOKENS = (
    "verified",
    "authentic",
    "provider",
    "ready",
    "backend",
    "provenance",
    "valid",
    "truthful",
    "quorum",
    "inclusion",
)

# --- Normative SREP transcript (packet SRC-RT19-SREP) -----------------------------------------------------
_SREP_CONTEXT = b"RoughTime v1 response signature\x00"
_SREP_CONTEXT_HEX = "526f75676854696d6520763120726573706f6e7365207369676e617475726500"
_SREP_CONTEXT_ASCII_LENGTH = 31
_SREP_CONTEXT_LENGTH = 32

# The CERT context is needed only to build the K5 prerequisite fixture, never to verify SREP.
_CERT_CONTEXT = b"RoughTime v1 delegation signature\x00"

# --- Accepted packet vectors (verbatim) -------------------------------------------------------------------
# V01_CERT_CONTEXT_CORRECT - supplies the K5 certificate prerequisite. Its DELE PUBK is exactly V05's key.
_V01_PUBLIC_KEY_HEX = "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8"
_V01_SIGNATURE_HEX = (
    "92c97ef4e509f01897fce1a4f71cf2375d8d5bbdbe4369bd6bf324ac1a235a9c752f981268424ce0b8feb48f55993b302adadb37"
    "12d02c848b1b447c4bbbf301"
)
_V01_DELE_RAW_HEX = (
    "040000002000000028000000300000005055424b4d494e544d4158545a5a5a5a29acbae141bccaf0b22e1a94d34d0bc7361e526d"
    "0bfe12c89794bc9322966dd76400000000000000c800000000000000a0a1a2a3"
)

# V05_SREP_CONTEXT_CORRECT - EXPECTED_RESULT ACCEPT, generator cryptography==46.0.7 / OpenSSL 3.5.6
_V05_MESSAGE_HEX = (
    "526f75676854696d6520763120726573706f6e7365207369676e61747572650006000000040000000800000010000000180000003800"
    "000056455200524144494d49445056455253524f4f545a5a5a5a01000000030000009600000000000000010000000100004032333435"
    "363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f5051b0b1b2b3"
)
_V05_PUBLIC_KEY_HEX = "29acbae141bccaf0b22e1a94d34d0bc7361e526d0bfe12c89794bc9322966dd7"
_V05_SIGNATURE_HEX = (
    "dc5df5e74771d83f8ba862e46a62e5cc04ddaa88d66535938a741b04d5a241b790178b1223f00fa685475e8c5c1a2bc12089c500"
    "70200b495296c3330e040b03"
)
_V05_SREP_RAW_HEX = (
    "06000000040000000800000010000000180000003800000056455200524144494d49445056455253524f4f545a5a5a5a0100000003"
    "0000009600000000000000010000000100004032333435363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f5051b0b1"
    "b2b3"
)
_V05_MIDP = 150

# V06_SREP_WRONG_CONTEXT - one ASCII case bit differs ("Response" instead of "response")
_V06_MESSAGE_HEX = (
    "526f75676854696d6520763120526573706f6e7365207369676e61747572650006000000040000000800000010000000180000003800"
    "000056455200524144494d49445056455253524f4f545a5a5a5a01000000030000009600000000000000010000000100004032333435"
    "363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f5051b0b1b2b3"
)

# V07_SREP_MISSING_NUL - exactly the trailing NUL omitted, 139 bytes
_V07_MESSAGE_HEX = (
    "526f75676854696d6520763120726573706f6e7365207369676e617475726506000000040000000800000010000000180000003800"
    "000056455200524144494d49445056455253524f4f545a5a5a5a010000000300000096000000000000000100000001000040323334"
    "35363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f5051b0b1b2b3"
)

# V08_SREP_REENCODED - generator PyNaCl==1.6.2 (REVERSE backend); re-encoding omits the preserved ZZZZ
_V08_PUBLIC_KEY_HEX = "174553b456dddfc6908ecab1c101fe6ab21e2baa0617795b7d43a63482993fd5"
_V08_SIGNATURE_HEX = (
    "a00dbbd148861f4e907023b3b9bc0c0f1b2302ce94000e890104ae25d5cb6b3072a398d95ce7cf3598919dc9ee05adea83898c13"
    "a4e0682e6de9e1600ff60900"
)
_V08_REENCODED_SREP_HEX = (
    "050000000400000008000000100000001800000056455200524144494d49445056455253524f4f5401000000030000009600000000"
    "000000010000000100004032333435363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f5051"
)

# V10_WRONG_DELEGATED_KEY - correct signature presented under a different delegated key
_V10_PUBLIC_KEY_HEX = "cd14b37f956e953194ff7fb73b3d81dcc561d61a7538094b7c3e1a643ee5f3aa"

# V12_SREP_ONE_BIT_MUTATION - final extension byte bit0 flipped (b3 -> b2)
_V12_SREP_RAW_HEX = (
    "06000000040000000800000010000000180000003800000056455200524144494d49445056455253524f4f545a5a5a5a0100000003"
    "0000009600000000000000010000000100004032333435363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f5051b0b1"
    "b2b2"
)

# V13/V14/V15/V16/V17/V18/V19 - shared Ed25519 encoding policy records
_V13_PUBLIC_KEY_HEX = "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531"
_V14_SIGNATURE_HEX = (
    "92c97ef4e509f01897fce1a4f71cf2375d8d5bbdbe4369bd6bf324ac1a235a9c752f981268424ce0b8feb48f55993b302adadb37"
    "12d02c848b1b447c4bbbf3"
)
_V15_SIGNATURE_HEX = (
    "92c97ef4e509f01897fce1a4f71cf2375d8d5bbdbe4369bd6bf324ac1a235a9cedd3f55c1a631258d69cf7a2def9de1400000000"
    "000000000000000000000010"
)
_V16_SIGNATURE_HEX = (
    "edffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f752f981268424ce0b8feb48f55993b302adadb37"
    "12d02c848b1b447c4bbbf301"
)
_V17_PUBLIC_KEY_HEX = "edffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f"
_V18_PUBLIC_KEY_HEX = "0100000000000000000000000000000000000000000000000000000000000000"
_V19_PUBLIC_KEY_HEX = "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05"

_V01_PUBLIC_KEY = bytes.fromhex(_V01_PUBLIC_KEY_HEX)
_V01_SIGNATURE = bytes.fromhex(_V01_SIGNATURE_HEX)
_V01_DELE_RAW = bytes.fromhex(_V01_DELE_RAW_HEX)
_V05_MESSAGE = bytes.fromhex(_V05_MESSAGE_HEX)
_V05_PUBLIC_KEY = bytes.fromhex(_V05_PUBLIC_KEY_HEX)
_V05_SIGNATURE = bytes.fromhex(_V05_SIGNATURE_HEX)
_V05_SREP_RAW = bytes.fromhex(_V05_SREP_RAW_HEX)
_V06_MESSAGE = bytes.fromhex(_V06_MESSAGE_HEX)
_V07_MESSAGE = bytes.fromhex(_V07_MESSAGE_HEX)
_V08_PUBLIC_KEY = bytes.fromhex(_V08_PUBLIC_KEY_HEX)
_V08_SIGNATURE = bytes.fromhex(_V08_SIGNATURE_HEX)
_V08_REENCODED_SREP = bytes.fromhex(_V08_REENCODED_SREP_HEX)
_V10_PUBLIC_KEY = bytes.fromhex(_V10_PUBLIC_KEY_HEX)
_V12_SREP_RAW = bytes.fromhex(_V12_SREP_RAW_HEX)
_V13_PUBLIC_KEY = bytes.fromhex(_V13_PUBLIC_KEY_HEX)
_V14_SIGNATURE = bytes.fromhex(_V14_SIGNATURE_HEX)
_V15_SIGNATURE = bytes.fromhex(_V15_SIGNATURE_HEX)
_V16_SIGNATURE = bytes.fromhex(_V16_SIGNATURE_HEX)
_V17_PUBLIC_KEY = bytes.fromhex(_V17_PUBLIC_KEY_HEX)
_V18_PUBLIC_KEY = bytes.fromhex(_V18_PUBLIC_KEY_HEX)
_V19_PUBLIC_KEY = bytes.fromhex(_V19_PUBLIC_KEY_HEX)

# The delegated PUBK the packet's DELE carries, at its documented offset inside the exact DELE value bytes.
_V01_DELEGATED_PUBLIC_KEY = _V01_DELE_RAW[32:64]

# --- Small-order inventory, pinned independently from the immutable libsodium source ----------------------
_SMALL_ORDER_ENCODINGS = (
    bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000"),
    bytes.fromhex("0100000000000000000000000000000000000000000000000000000000000000"),
    bytes.fromhex("26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05"),
    bytes.fromhex("c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a"),
    bytes.fromhex("ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f"),
    bytes.fromhex("edffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f"),
    bytes.fromhex("eeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f"),
)
_SMALL_ORDER_COUNT = 7
_GROUP_ORDER = (1 << 252) + 27742317777372353535851937790883648493
_FIELD_PRIME = (1 << 255) - 19


def _sign_bit_toggled(encoding: bytes) -> bytes:
    return encoding[:31] + bytes((encoding[31] ^ 0x80,))


_SIGN_BIT_TOGGLED_SMALL_ORDER = tuple(_sign_bit_toggled(entry) for entry in _SMALL_ORDER_ENCODINGS)
# Entries 5 and 6 encode y = p and y = p + 1, which are NON-canonical; the canonicality gate fires on those
# before the small-order gate. Recorded so the two rejection causes stay distinguishable.
_CANONICAL_SMALL_ORDER_INDEXES = (0, 1, 2, 3, 4)
_NONCANONICAL_SMALL_ORDER_INDEXES = (5, 6)

_MAGIC = b"ROUGHTIM"
_TAG_SIG = b"SIG\x00"
_TAG_NONC = b"NONC"
_TAG_TYPE = b"TYPE"
_TAG_PATH = b"PATH"
_TAG_SREP = b"SREP"
_TAG_CERT = b"CERT"
_TAG_INDX = b"INDX"
_TAG_DELE = b"DELE"


# --- Test-only encoders (independent of every production encoder) -----------------------------------------
def _le(tag: bytes) -> int:
    return int.from_bytes(tag, "little")


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "little")


def _encode_message(pairs: list[tuple[bytes, bytes]]) -> bytes:
    ordered = sorted(pairs, key=lambda pair: _le(pair[0]))
    out = _u32(len(ordered))
    cumulative = 0
    for index in range(len(ordered) - 1):
        cumulative += len(ordered[index][1])
        out += _u32(cumulative)
    for tag, _ in ordered:
        out += tag
    for _, value in ordered:
        out += value
    return out


def _encode_packet(message: bytes) -> bytes:
    return _MAGIC + _u32(len(message)) + message


def _cert_raw(*, signature: bytes = _V01_SIGNATURE, dele: bytes = _V01_DELE_RAW) -> bytes:
    return _encode_message([(_TAG_SIG, signature), (_TAG_DELE, dele)])


def _response_packet(
    *,
    response_signature: bytes = _V05_SIGNATURE,
    srep: bytes = _V05_SREP_RAW,
    cert_signature: bytes = _V01_SIGNATURE,
    dele: bytes = _V01_DELE_RAW,
) -> bytes:
    """Embed the packet's EXACT SREP/CERT/DELE value bytes so K2 preserves them verbatim."""
    outer = _encode_message(
        [
            (_TAG_SIG, response_signature),
            (_TAG_NONC, bytes(32)),
            (_TAG_TYPE, _u32(1)),
            (_TAG_PATH, b""),
            (_TAG_SREP, srep),
            (_TAG_CERT, _cert_raw(signature=cert_signature, dele=dele)),
            (_TAG_INDX, _u32(0)),
        ]
    )
    return _encode_packet(outer)


def _response(**kwargs) -> RoughtimeV19ResponseSemantics:
    return parse_roughtime_v19_response(_response_packet(**kwargs))


def _certificate(**kwargs) -> RoughtimeV19CertificateVerification:
    """The verified K5 prerequisite artifact for the same response."""
    return verify_roughtime_v19_certificate(_response(**kwargs), _V01_PUBLIC_KEY)


def _artifact(**kwargs) -> RoughtimeV19SignedResponseVerification:
    return verify_roughtime_v19_signed_response(_certificate(**kwargs))


def _hollow(cls, **fields):
    obj = object.__new__(cls)
    for name, value in fields.items():
        object.__setattr__(obj, name, value)
    return obj


def _registered_state(artifact: RoughtimeV19SignedResponseVerification) -> tuple:
    """The verified values, obtained through the public validating reducer (never the registry)."""
    reducer, arguments = artifact.__reduce__()
    assert reducer.__name__ == "_rebuild_signed_response_verification"
    state = arguments[0]
    assert type(state) is tuple
    return state


def _valid_artifact_fields() -> dict:
    return dict(zip(_EXPECTED_ARTIFACT_FIELDS, _registered_state(_artifact())))


_PRODUCTION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "crypto_core"
    / "validation"
    / "roughtime_v19_signed_response_verification.py"
)


def _production_tree() -> ast.Module:
    return ast.parse(_PRODUCTION_PATH.read_text(encoding="utf-8"))


def _backend_rejects(message: bytes, public_key: bytes, signature: bytes) -> bool:
    """Ask the pinned backend directly, independently of the K5-SREP verifier."""
    from nacl.encoding import RawEncoder
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey

    try:
        VerifyKey(public_key, encoder=RawEncoder).verify(message, signature)
    except BadSignatureError:
        return True
    return False


# ============================================================================================================
# Normative transcript
# ============================================================================================================
def test_srep_context_is_exact_with_trailing_nul() -> None:
    assert _SREP_CONTEXT.hex() == _SREP_CONTEXT_HEX
    assert len(_SREP_CONTEXT) == _SREP_CONTEXT_LENGTH == 32
    assert _SREP_CONTEXT.endswith(b"\x00")
    assert _SREP_CONTEXT[:-1] == b"RoughTime v1 response signature"
    assert len(_SREP_CONTEXT[:-1]) == _SREP_CONTEXT_ASCII_LENGTH == 31


def test_v05_transcript_is_context_plus_exact_srep() -> None:
    assert _V05_MESSAGE == _SREP_CONTEXT + _V05_SREP_RAW
    assert len(_V05_MESSAGE) == 140
    assert len(_V05_SREP_RAW) == 108


def test_production_pins_the_exact_srep_context_constant() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    assert 'b"RoughTime v1 response signature\\x00"' in source


def test_srep_context_differs_from_the_cert_context() -> None:
    """The two layers must never share a transcript prefix."""
    assert _SREP_CONTEXT != _CERT_CONTEXT
    assert len(_CERT_CONTEXT) == 34
    assert not _V05_MESSAGE.startswith(_CERT_CONTEXT)


# ============================================================================================================
# Positive coverage
# ============================================================================================================
def test_v05_srep_context_correct_verifies() -> None:
    artifact = _artifact()
    assert artifact.delegated_public_key == _V05_PUBLIC_KEY
    assert artifact.response_signature == _V05_SIGNATURE
    assert artifact.signed_response_raw == _V05_SREP_RAW
    assert artifact.signed_midpoint == _V05_MIDP


def test_packet_delegated_key_equals_the_dele_pubk() -> None:
    """The packet is internally consistent: V05's key IS the delegated key V01's DELE carries."""
    assert _V05_PUBLIC_KEY == _V01_DELEGATED_PUBLIC_KEY
    assert _V05_PUBLIC_KEY != _V01_PUBLIC_KEY


def test_verifier_artifact_carries_exact_k2_derived_values() -> None:
    response = _response()
    artifact = _artifact()
    assert artifact.response_raw == response.raw
    assert artifact.signed_response_raw == response.signed_response.raw
    assert artifact.signed_root == response.signed_response.root
    assert artifact.signed_midpoint == response.signed_response.midpoint_seconds
    assert artifact.signed_radius == response.signed_response.radius_seconds
    assert artifact.signed_version == response.signed_response.version
    assert artifact.signed_versions == response.signed_response.versions
    assert artifact.long_term_public_key == _V01_PUBLIC_KEY


def test_exact_preserved_srep_includes_the_unknown_extension() -> None:
    response = _response()
    assert response.signed_response.raw.endswith(b"\xb0\xb1\xb2\xb3")
    assert len(response.signed_response.extensions) == 1


def test_direct_artifact_construction_succeeds() -> None:
    artifact = RoughtimeV19SignedResponseVerification(**_valid_artifact_fields())
    assert artifact.signed_response_raw == _V05_SREP_RAW


def test_equality_and_hashing_are_deterministic() -> None:
    first = _artifact()
    second = _artifact()
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1


def test_v08_reverse_generator_positive_verifies_through_production() -> None:
    """V08 as a POSITIVE: cross-backend in the opposite direction to V05.

    V05 was generated by cryptography/OpenSSL. V08's packet record states GENERATOR_IMPLEMENTATION
    PyNaCl==1.6.2 with the base exact transcript "cross-verified positive", so verifying V08's signature over
    the EXACT preserved 108-byte SREP exercises the reverse generator direction: signed by libsodium, verified
    through production K5-SREP. Its DELE must carry V08's key so the delegated-key rebinding succeeds.
    """
    assert _V08_PUBLIC_KEY != _V05_PUBLIC_KEY
    assert _V08_SIGNATURE != _V05_SIGNATURE
    dele = _dele_with_pubk(_V08_PUBLIC_KEY)
    certificate = verify_roughtime_v19_certificate(
        _response(response_signature=_V08_SIGNATURE, dele=dele, cert_signature=_cert_signature_for(dele)),
        _long_term_key_for(dele),
    )
    artifact = verify_roughtime_v19_signed_response(certificate)
    assert artifact.delegated_public_key == _V08_PUBLIC_KEY
    assert artifact.response_signature == _V08_SIGNATURE
    assert artifact.signed_response_raw == _V05_SREP_RAW
    assert len(artifact.signed_response_raw) == 108


# ============================================================================================================
# Negative SREP coverage (packet vectors)
# ============================================================================================================
def test_v06_wrong_context_transcript_does_not_verify() -> None:
    """V06 flips one ASCII case bit in the context; the verifier's pinned context can never produce it."""
    assert _V06_MESSAGE != _V05_MESSAGE
    assert _V06_MESSAGE[:_SREP_CONTEXT_LENGTH] != _SREP_CONTEXT
    assert _V06_MESSAGE[_SREP_CONTEXT_LENGTH:] == _V05_SREP_RAW
    assert _backend_rejects(_V06_MESSAGE, _V05_PUBLIC_KEY, _V05_SIGNATURE)
    assert not _backend_rejects(_V05_MESSAGE, _V05_PUBLIC_KEY, _V05_SIGNATURE)


def test_v07_missing_trailing_nul_transcript_does_not_verify() -> None:
    """V07 omits exactly the trailing NUL, proving the NUL is load-bearing in the signed input."""
    assert len(_V07_MESSAGE) == 139
    assert _V07_MESSAGE == b"RoughTime v1 response signature" + _V05_SREP_RAW
    assert _backend_rejects(_V07_MESSAGE, _V05_PUBLIC_KEY, _V05_SIGNATURE)


def test_v08_reencoded_srep_rejected() -> None:
    """Re-encoding drops the preserved ZZZZ extension, so the signature over the exact bytes fails."""
    assert len(_V08_REENCODED_SREP) == 96
    assert _V08_REENCODED_SREP != _V05_SREP_RAW
    dele = _dele_with_pubk(_V08_PUBLIC_KEY)
    certificate = verify_roughtime_v19_certificate(
        _response(
            response_signature=_V08_SIGNATURE,
            srep=_V08_REENCODED_SREP,
            dele=dele,
            cert_signature=_cert_signature_for(dele),
        ),
        _long_term_key_for(dele),
    )
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(certificate)
    assert excinfo.value.reason is R.SREP_SIGNATURE_INVALID


def test_v10_wrong_delegated_key_rejected() -> None:
    """The signature is correct but the DELE carries a different delegated key."""
    dele = _dele_with_pubk(_V10_PUBLIC_KEY)
    certificate = verify_roughtime_v19_certificate(
        _response(dele=dele, cert_signature=_cert_signature_for(dele)),
        _long_term_key_for(dele),
    )
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(certificate)
    assert excinfo.value.reason is R.SREP_SIGNATURE_INVALID


def test_v12_one_bit_srep_mutation_rejected() -> None:
    assert _V12_SREP_RAW != _V05_SREP_RAW
    assert len(_V12_SREP_RAW) == len(_V05_SREP_RAW)
    assert sum(a != b for a, b in zip(_V12_SREP_RAW, _V05_SREP_RAW)) == 1
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(_certificate(srep=_V12_SREP_RAW))
    assert excinfo.value.reason is R.SREP_SIGNATURE_INVALID


def test_long_term_key_is_never_used_to_verify_the_outer_signature() -> None:
    """Presenting the response SIG under the LONG-TERM key must fail at the backend."""
    assert _backend_rejects(_V05_MESSAGE, _V01_PUBLIC_KEY, _V05_SIGNATURE)
    assert not _backend_rejects(_V05_MESSAGE, _V05_PUBLIC_KEY, _V05_SIGNATURE)


def test_v15_scalar_s_equal_to_group_order_rejected() -> None:
    assert int.from_bytes(_V15_SIGNATURE[32:], "little") == _GROUP_ORDER
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(_certificate(response_signature=_V15_SIGNATURE))
    assert excinfo.value.reason is R.SREP_SIGNATURE_INVALID


def test_scalar_s_above_group_order_rejected() -> None:
    signature = _V05_SIGNATURE[:32] + (_GROUP_ORDER + 1).to_bytes(32, "little")
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(_certificate(response_signature=signature))
    assert excinfo.value.reason is R.SREP_SIGNATURE_INVALID


def test_v16_noncanonical_r_rejected() -> None:
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(_certificate(response_signature=_V16_SIGNATURE))
    assert excinfo.value.reason is R.SREP_SIGNATURE_INVALID


@pytest.mark.parametrize("index", range(_SMALL_ORDER_COUNT))
def test_every_small_order_encoding_rejected_as_signature_r(index) -> None:
    signature = _SMALL_ORDER_ENCODINGS[index] + _V05_SIGNATURE[32:]
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(_certificate(response_signature=signature))
    assert excinfo.value.reason is R.SREP_SIGNATURE_INVALID


@pytest.mark.parametrize("index", range(_SMALL_ORDER_COUNT))
def test_sign_bit_toggled_small_order_rejected_as_signature_r(index) -> None:
    signature = _SIGN_BIT_TOGGLED_SMALL_ORDER[index] + _V05_SIGNATURE[32:]
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(_certificate(response_signature=signature))
    assert excinfo.value.reason is R.SREP_SIGNATURE_INVALID, index


def test_v14_short_signature_is_rejected_at_the_k2_boundary() -> None:
    """A 63-byte outer SIG cannot survive K2's exact length rule, so it never reaches SREP verification."""
    assert len(_V14_SIGNATURE) == 63
    with pytest.raises(Exception) as excinfo:
        parse_roughtime_v19_response(_response_packet(response_signature=_V14_SIGNATURE))
    assert type(excinfo.value) is not RoughtimeV19SignedResponseVerificationError


# ============================================================================================================
# Delegated public-key policy
# ============================================================================================================
def _dele_with_pubk(pubk: bytes) -> bytes:
    """Rebuild a DELE carrying a chosen PUBK with the packet's exact MINT/MAXT/ZZZZ, test-only encoder."""
    return _encode_message(
        [
            (b"PUBK", pubk),
            (b"MINT", _V01_DELE_RAW[64:72]),
            (b"MAXT", _V01_DELE_RAW[72:80]),
            (b"ZZZZ", _V01_DELE_RAW[80:84]),
        ]
    )


_DELE_KEYPAIRS: dict[bytes, tuple[bytes, bytes]] = {}


def _register_dele_keypair(dele: bytes) -> tuple[bytes, bytes]:
    """Deterministically sign a rebuilt DELE so a valid K5 prerequisite exists for it.

    Test-only signing: the production module never signs. The long-term keypair is derived from a fixed
    disclosed seed so the fixture is fully deterministic and carries no secret.
    """
    if dele in _DELE_KEYPAIRS:
        return _DELE_KEYPAIRS[dele]
    from nacl.encoding import RawEncoder
    from nacl.signing import SigningKey

    signing_key = SigningKey(bytes(range(32)), encoder=RawEncoder)
    long_term_public_key = bytes(signing_key.verify_key)
    signature = signing_key.sign(_CERT_CONTEXT + dele).signature
    _DELE_KEYPAIRS[dele] = (long_term_public_key, signature)
    return _DELE_KEYPAIRS[dele]


def _long_term_key_for(dele: bytes) -> bytes:
    return _register_dele_keypair(dele)[0]


def _cert_signature_for(dele: bytes) -> bytes:
    return _register_dele_keypair(dele)[1]


@pytest.mark.parametrize(
    ("label", "key"),
    [
        ("V13_length_31", _V13_PUBLIC_KEY),
        ("length_33", _V05_PUBLIC_KEY + b"\x00"),
        ("V17_noncanonical_a", _V17_PUBLIC_KEY),
        ("V18_identity", _V18_PUBLIC_KEY),
        ("V19_order8", _V19_PUBLIC_KEY),
        ("all_zero", bytes(32)),
    ],
)
def test_invalid_delegated_public_key_rejected(label, key) -> None:
    """A DELE whose PUBK fails encoding policy must close as delegated_public_key_invalid."""
    if len(key) != 32:
        pytest.skip("K2 enforces the exact 32-byte PUBK length before K5-SREP sees the response")
    dele = _dele_with_pubk(key)
    certificate = verify_roughtime_v19_certificate(
        _response(dele=dele, cert_signature=_cert_signature_for(dele)),
        _long_term_key_for(dele),
    )
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(certificate)
    assert excinfo.value.reason is R.DELEGATED_PUBLIC_KEY_INVALID, label


@pytest.mark.parametrize("index", range(_SMALL_ORDER_COUNT))
def test_every_small_order_encoding_rejected_as_delegated_key(index) -> None:
    dele = _dele_with_pubk(_SMALL_ORDER_ENCODINGS[index])
    certificate = verify_roughtime_v19_certificate(
        _response(dele=dele, cert_signature=_cert_signature_for(dele)),
        _long_term_key_for(dele),
    )
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(certificate)
    assert excinfo.value.reason is R.DELEGATED_PUBLIC_KEY_INVALID, index


@pytest.mark.parametrize("index", range(_SMALL_ORDER_COUNT))
def test_sign_bit_toggled_small_order_rejected_as_delegated_key(index) -> None:
    dele = _dele_with_pubk(_SIGN_BIT_TOGGLED_SMALL_ORDER[index])
    certificate = verify_roughtime_v19_certificate(
        _response(dele=dele, cert_signature=_cert_signature_for(dele)),
        _long_term_key_for(dele),
    )
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(certificate)
    assert excinfo.value.reason is R.DELEGATED_PUBLIC_KEY_INVALID, index


@pytest.mark.parametrize(
    ("label", "key"),
    [
        ("V13_length_31", _V13_PUBLIC_KEY),
        ("length_33", _V05_PUBLIC_KEY + b"\x00"),
        ("empty", b""),
        ("length_0_padded", bytes(31)),
    ],
)
def test_delegated_key_length_policy_is_pinned_directly(label, key) -> None:
    """K2's exact 32-byte PUBK rule fires before K5-SREP, so the length policy is pinned white-box here.

    Without this the length branch of `_public_key_rejected` could be deleted and every end-to-end test would
    still pass, because no reachable K2-parsable response can carry a wrong-length PUBK.
    """
    from crypto_core.validation.roughtime_v19_signed_response_verification import _public_key_rejected

    assert len(key) != 32
    assert _public_key_rejected(key) is True, label
    assert _public_key_rejected(_V05_PUBLIC_KEY) is False


@pytest.mark.parametrize(
    ("label", "signature"),
    [("V14_length_63", _V14_SIGNATURE), ("length_65", _V05_SIGNATURE + b"\x00"), ("empty", b"")],
)
def test_response_signature_length_policy_is_pinned_directly(label, signature) -> None:
    """K2's exact 64-byte SIG rule fires before K5-SREP, so the length policy is pinned white-box here."""
    from crypto_core.validation.roughtime_v19_signed_response_verification import _signature_rejected

    assert len(signature) != 64
    assert _signature_rejected(signature) is True, label
    assert _signature_rejected(_V05_SIGNATURE) is False


def test_delegated_key_rebinding_is_pinned_directly() -> None:
    """White-box: the canonical DELE PUBK must equal the supplied delegated key.

    A K5 artifact always derives its delegated key from its own reparse, so the mismatch is unreachable
    end-to-end today. Pinning it at the function boundary keeps the guard causally proven, so a future K5
    change cannot silently remove the rebinding.
    """
    from crypto_core.validation.roughtime_v19_signed_response_verification import _verified_state

    packet = _response_packet()
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        _verified_state(packet, _V01_PUBLIC_KEY, _V10_PUBLIC_KEY, R.INPUT_ARTIFACT_INCONSISTENT)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT
    # The genuine delegated key still succeeds through the same entry point.
    _verified_state(packet, _V01_PUBLIC_KEY, _V01_DELEGATED_PUBLIC_KEY, R.INPUT_ARTIFACT_INCONSISTENT)


@pytest.mark.parametrize("index", range(_SMALL_ORDER_COUNT))
def test_small_order_r_is_rejected_by_our_policy_not_only_by_the_backend(index) -> None:
    """libsodium also rejects a small-order R, so this pins OUR layer independently."""
    from crypto_core.validation.roughtime_v19_signed_response_verification import _signature_rejected

    signature = _SMALL_ORDER_ENCODINGS[index] + _V05_SIGNATURE[32:]
    assert _signature_rejected(signature) is True, index
    toggled = _SIGN_BIT_TOGGLED_SMALL_ORDER[index] + _V05_SIGNATURE[32:]
    assert _signature_rejected(toggled) is True, index


@pytest.mark.parametrize("index", range(_SMALL_ORDER_COUNT))
def test_small_order_a_is_rejected_by_our_policy_not_only_by_the_backend(index) -> None:
    from crypto_core.validation.roughtime_v19_signed_response_verification import _public_key_rejected

    assert _public_key_rejected(_SMALL_ORDER_ENCODINGS[index]) is True, index
    assert _public_key_rejected(_SIGN_BIT_TOGGLED_SMALL_ORDER[index]) is True, index


def test_registry_revalidation_rejects_planted_but_well_shaped_wrong_state() -> None:
    """Proves the per-consumption cryptographic revalidation is load-bearing, not just a shape check.

    Plants a state tuple that is exactly the right shape and exact types but cryptographically wrong, so only
    the full re-derivation can catch it. Uses the closure path, which is explicitly OUTSIDE the supported
    trust boundary and exists here solely to prove the revalidation step.
    """
    registry = _closure_registry()
    genuine = _artifact()
    state = list(_registered_state(genuine))
    state[6] = state[6] + 1  # signed_midpoint: right type, wrong value, not covered by the signature
    forged = tuple(state)
    victim = _artifact()
    key = id(victim)
    original = registry[key]
    registry[key] = (weakref.ref(victim), forged)
    try:
        for consume in (lambda obj: obj.signed_midpoint, repr, hash, lambda obj: obj.__reduce__()):
            with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
                consume(victim)
            assert excinfo.value.reason is R.ARTIFACT_SIGNED_RESPONSE_VERIFICATION_INCONSISTENT
    finally:
        registry[key] = original
    assert victim.signed_midpoint == _V05_MIDP


_FORBIDDEN_PUBLIC_ATTRIBUTES = (
    "readiness_promoted",
    "provider",
    "provider_id",
    "authentic",
    "verified",
    "time_valid",
    "truthful",
    "quorum",
    "quorum_ready",
    "ready",
    "root_authentic",
    "request_included",
    "deployed_version",
)


@pytest.mark.parametrize("name", _FORBIDDEN_PUBLIC_ATTRIBUTES)
def test_artifact_exposes_no_overclaiming_attribute(name) -> None:
    """No provider / readiness / truthful-time / quorum / inclusion surface may exist, on class or instance."""
    artifact = _artifact()
    assert not hasattr(RoughtimeV19SignedResponseVerification, name), name
    assert not hasattr(artifact, name), name


def test_public_attribute_surface_is_exactly_the_declared_fields() -> None:
    """Closes the overclaim surface completely: no extra public attribute of any kind."""
    artifact = _artifact()
    public = {
        name for name in dir(artifact) if not name.startswith("_") and not callable(getattr(type(artifact), name, None))
    }
    assert public == set(_EXPECTED_ARTIFACT_FIELDS)


def test_repository_policy_rejects_scalar_s_at_or_above_l_independently_of_the_backend() -> None:
    from crypto_core.validation.roughtime_v19_signed_response_verification import _signature_rejected

    canonical_r = _V05_SIGNATURE[:32]
    assert _signature_rejected(canonical_r + _GROUP_ORDER.to_bytes(32, "little")) is True
    assert _signature_rejected(canonical_r + (_GROUP_ORDER + 1).to_bytes(32, "little")) is True
    assert _signature_rejected(canonical_r + (_GROUP_ORDER - 1).to_bytes(32, "little")) is False
    assert _signature_rejected(_V05_SIGNATURE) is False


def test_repository_policy_rejects_noncanonical_points_independently_of_the_backend() -> None:
    """White-box: uses y = p + 2, non-canonical yet NOT in the small-order inventory."""
    from crypto_core.validation.roughtime_v19_signed_response_verification import (
        _public_key_rejected,
        _signature_rejected,
    )

    non_canonical = (_FIELD_PRIME + 2).to_bytes(32, "little")
    assert non_canonical not in _SMALL_ORDER_ENCODINGS
    assert _public_key_rejected(non_canonical) is True
    assert _signature_rejected(non_canonical + _V05_SIGNATURE[32:]) is True
    assert _public_key_rejected(_V05_PUBLIC_KEY) is False


def test_byte_31_masking_in_the_small_order_policy_is_pinned_directly() -> None:
    """Pins the masking rule itself, independently of which gate fires first end-to-end."""
    from crypto_core.validation.roughtime_v19_signed_response_verification import (
        _is_canonical_point,
        _is_small_order,
    )

    for index, (original, toggled) in enumerate(zip(_SMALL_ORDER_ENCODINGS, _SIGN_BIT_TOGGLED_SMALL_ORDER)):
        assert _is_small_order(original) is True, index
        assert _is_small_order(toggled) is True, index
        assert _is_canonical_point(original) is _is_canonical_point(toggled), index
    for index in _CANONICAL_SMALL_ORDER_INDEXES:
        assert _is_canonical_point(_SMALL_ORDER_ENCODINGS[index]) is True, index
    for index in _NONCANONICAL_SMALL_ORDER_INDEXES:
        assert _is_canonical_point(_SMALL_ORDER_ENCODINGS[index]) is False, index


def test_hardening_constants_are_the_exact_rfc8032_values() -> None:
    from crypto_core.validation.roughtime_v19_signed_response_verification import _FIELD_PRIME as production_p
    from crypto_core.validation.roughtime_v19_signed_response_verification import (
        _GROUP_ORDER as production_l,
    )

    assert production_p == (1 << 255) - 19
    assert production_l == _GROUP_ORDER
    assert production_l == 7237005577332262213973186563042994240857116359379907606001950938285454250989


def test_production_small_order_inventory_exactly_equals_the_pinned_oracle() -> None:
    """EXACT equality against the independently pinned tuple, not presence in the production source text."""
    from crypto_core.validation.roughtime_v19_signed_response_verification import (
        _SMALL_ORDER_ENCODINGS as production_inventory,
    )

    assert type(production_inventory) is tuple
    assert len(production_inventory) == _SMALL_ORDER_COUNT == 7
    for entry in production_inventory:
        assert type(entry) is bytes
        assert len(entry) == 32
    assert production_inventory == _SMALL_ORDER_ENCODINGS
    for index in range(_SMALL_ORDER_COUNT):
        assert production_inventory[index] == _SMALL_ORDER_ENCODINGS[index], index
    assert len(set(production_inventory)) == _SMALL_ORDER_COUNT


@pytest.mark.parametrize("extra", [bytes(32), bytes.fromhex("02" * 32)])
def test_an_extra_production_inventory_entry_would_break_exact_equality(extra) -> None:
    from crypto_core.validation.roughtime_v19_signed_response_verification import (
        _SMALL_ORDER_ENCODINGS as production_inventory,
    )

    assert (*production_inventory, extra) != _SMALL_ORDER_ENCODINGS
    assert production_inventory[:-1] != _SMALL_ORDER_ENCODINGS
    assert tuple(reversed(production_inventory)) != _SMALL_ORDER_ENCODINGS


def test_production_does_not_import_any_private_k5_symbol() -> None:
    """The independent policy must be its own; importing K5 privates would couple the two layers."""
    imported: set[str] = set()
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(f"{node.module}.{alias.name}")
    for name in imported:
        if "roughtime_v19_certificate_verification" in name:
            assert name.endswith(".RoughtimeV19CertificateVerification"), name


# ============================================================================================================
# Backend failure normalization
# ============================================================================================================
class _CustomBackendFailure(Exception):
    """A backend exception class the production module cannot possibly have enumerated."""


_BACKEND_FAILURE_CLASSES = (
    AttributeError,
    IndexError,
    ValueError,  # builtins.ValueError, NOT nacl.exceptions.ValueError
    TypeError,
    RuntimeError,
    OSError,
    _CustomBackendFailure,
)


@pytest.mark.parametrize("failure", _BACKEND_FAILURE_CLASSES, ids=lambda cls: cls.__name__)
def test_unexpected_backend_exception_from_verify_normalizes_to_backend_failure(failure, monkeypatch) -> None:
    import crypto_core.validation.roughtime_v19_signed_response_verification as module

    certificate = _certificate()

    class _Failing:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def verify(self, *args, **kwargs):
            raise failure("backend detail that must not leak")

    monkeypatch.setattr(module, "VerifyKey", _Failing)
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(certificate)
    assert excinfo.value.reason is R.CRYPTO_BACKEND_FAILURE
    assert str(excinfo.value) == "crypto_backend_failure"
    assert "backend detail" not in str(excinfo.value)


@pytest.mark.parametrize("failure", _BACKEND_FAILURE_CLASSES, ids=lambda cls: cls.__name__)
def test_unexpected_backend_exception_from_construction_normalizes(failure, monkeypatch) -> None:
    import crypto_core.validation.roughtime_v19_signed_response_verification as module

    certificate = _certificate()

    def _failing_key(*args, **kwargs):
        raise failure("constructor detail that must not leak")

    monkeypatch.setattr(module, "VerifyKey", _failing_key)
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(certificate)
    assert excinfo.value.reason is R.CRYPTO_BACKEND_FAILURE
    assert "constructor detail" not in str(excinfo.value)


def test_bad_signature_error_maps_to_srep_signature_invalid(monkeypatch) -> None:
    from nacl.exceptions import BadSignatureError

    import crypto_core.validation.roughtime_v19_signed_response_verification as module

    certificate = _certificate()
    calls: list[int] = []

    class _Failing:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def verify(self, *args, **kwargs):
            calls.append(1)
            # Let the CERT re-proof succeed, fail only the SREP verification.
            if len(calls) < 2:
                return None
            raise BadSignatureError("forged")

    monkeypatch.setattr(module, "VerifyKey", _Failing)
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(certificate)
    assert excinfo.value.reason is R.SREP_SIGNATURE_INVALID


def test_nacl_valueerror_maps_to_srep_signature_invalid(monkeypatch) -> None:
    """Precedence matters: nacl's ValueError must be handled BEFORE the broad Exception catch."""
    from nacl.exceptions import ValueError as NaclValueError

    import crypto_core.validation.roughtime_v19_signed_response_verification as module

    assert NaclValueError is not ValueError
    certificate = _certificate()
    calls: list[int] = []

    class _Failing:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def verify(self, *args, **kwargs):
            calls.append(1)
            if len(calls) < 2:
                return None
            raise NaclValueError("bad encoding")

    monkeypatch.setattr(module, "VerifyKey", _Failing)
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(certificate)
    assert excinfo.value.reason is R.SREP_SIGNATURE_INVALID


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_base_exception_from_backend_is_not_swallowed(interrupt, monkeypatch) -> None:
    import crypto_core.validation.roughtime_v19_signed_response_verification as module

    certificate = _certificate()

    class _Failing:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def verify(self, *args, **kwargs):
            raise interrupt()

    monkeypatch.setattr(module, "VerifyKey", _Failing)
    with pytest.raises(interrupt):
        verify_roughtime_v19_signed_response(certificate)


def _enclosing_function_names(tree: ast.Module) -> dict[ast.ExceptHandler, str]:
    owner: dict[ast.ExceptHandler, str] = {}
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        current = parents.get(node)
        while current is not None and not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            current = parents.get(current)
        owner[node] = current.name if current is not None else "<module>"
    return owner


def test_production_never_catches_base_exception() -> None:
    """No BaseException-family catch, and broad `except Exception` only at authorized boundaries."""
    tree = _production_tree()
    owner = _enclosing_function_names(tree)
    broad_catch_functions = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        names = [child.id for child in ast.walk(node.type) if isinstance(child, ast.Name)]
        for forbidden in ("BaseException", "KeyboardInterrupt", "SystemExit", "GeneratorExit"):
            assert forbidden not in names
        if "Exception" in names:
            broad_catch_functions.append(owner[node])
    assert sorted(broad_catch_functions) == ["_verify_detached", "verify_roughtime_v19_signed_response"]


def test_no_raw_backend_exception_leaks() -> None:
    for signature in (_V15_SIGNATURE, _V16_SIGNATURE):
        with pytest.raises(RoughtimeV19SignedResponseVerificationError):
            verify_roughtime_v19_signed_response(_certificate(response_signature=signature))


# ============================================================================================================
# Input trust boundary
# ============================================================================================================
_HOSTILE_ACCESS: list[str] = []


@pytest.mark.parametrize("bad", [object(), None, b"", 0, "artifact", _V05_PUBLIC_KEY])
def test_wrong_input_type_rejected(bad) -> None:
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(bad)
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_k2_response_is_not_accepted_in_place_of_a_k5_artifact() -> None:
    """The prerequisite is the VERIFIED certificate artifact, never a bare parsed response."""
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(_response())
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_hollow_k5_artifact_fails_closed() -> None:
    hollow = object.__new__(RoughtimeV19CertificateVerification)
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(hollow)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_k5_artifact_subclass_is_impossible_so_no_override_can_run() -> None:
    """K5 is sealed, so a hostile subclass cannot even be defined - the strongest possible form."""
    with pytest.raises(TypeError):

        class _Hostile(RoughtimeV19CertificateVerification):
            pass


def test_wrong_input_type_precedes_artifact_consistency() -> None:
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(object())
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_delegated_key_policy_precedes_signature_policy() -> None:
    """An invalid delegated key must win over an also-invalid response signature."""
    dele = _dele_with_pubk(_V18_PUBLIC_KEY)
    certificate = verify_roughtime_v19_certificate(
        _response(response_signature=_V16_SIGNATURE, dele=dele, cert_signature=_cert_signature_for(dele)),
        _long_term_key_for(dele),
    )
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        verify_roughtime_v19_signed_response(certificate)
    assert excinfo.value.reason is R.DELEGATED_PUBLIC_KEY_INVALID


# ============================================================================================================
# Output artifact contract
# ============================================================================================================
def test_artifact_declares_exactly_ten_public_fields_in_order() -> None:
    from crypto_core.validation.roughtime_v19_signed_response_verification import _VERIFICATION_FIELD_NAMES

    assert _VERIFICATION_FIELD_NAMES == _EXPECTED_ARTIFACT_FIELDS
    assert len(_VERIFICATION_FIELD_NAMES) == 10
    for name in _EXPECTED_ARTIFACT_FIELDS:
        assert type(getattr(RoughtimeV19SignedResponseVerification, name)) is property


def test_storage_order_equals_declared_public_field_order() -> None:
    artifact = _artifact()
    state = _registered_state(artifact)
    assert len(state) == 10
    for index, name in enumerate(_EXPECTED_ARTIFACT_FIELDS):
        assert state[index] == getattr(artifact, name), name


def test_artifact_field_names_avoid_forbidden_tokens() -> None:
    for name in _EXPECTED_ARTIFACT_FIELDS:
        for token in _FORBIDDEN_FIELD_TOKENS:
            assert token not in name


def test_signed_fields_are_named_signed_not_true() -> None:
    """Naming discipline: the artifact must not imply truthful time or a deployed-version claim."""
    for name in ("signed_root", "signed_midpoint", "signed_radius", "signed_version", "signed_versions"):
        assert name.startswith("signed_")
    for forbidden in ("true_", "actual_", "trusted_", "current_", "wall_", "utc_"):
        for name in _EXPECTED_ARTIFACT_FIELDS:
            assert not name.startswith(forbidden)


def test_artifact_inherits_no_builtin_container_or_scalar_base() -> None:
    assert RoughtimeV19SignedResponseVerification.__mro__ == (RoughtimeV19SignedResponseVerification, object)
    assert RoughtimeV19SignedResponseVerification.__bases__ == (object,)
    for forbidden in (tuple, list, dict, set, frozenset, bytes, bytearray, str, int, float):
        assert not issubclass(RoughtimeV19SignedResponseVerification, forbidden), forbidden
    assert RoughtimeV19SignedResponseVerification.__name__ == "RoughtimeV19SignedResponseVerification"
    assert RoughtimeV19SignedResponseVerification.__qualname__ == "RoughtimeV19SignedResponseVerification"
    assert (
        RoughtimeV19SignedResponseVerification.__module__
        == "crypto_core.validation.roughtime_v19_signed_response_verification"
    )


def test_artifact_has_no_instance_dict_and_only_a_weakref_slot() -> None:
    artifact = _artifact()
    assert RoughtimeV19SignedResponseVerification.__slots__ == ("__weakref__",)
    assert not hasattr(artifact, "__dict__")
    assert type(artifact).__dictoffset__ == 0
    assert "__dict__" not in dir(artifact)


def test_vars_on_artifact_fails() -> None:
    with pytest.raises(TypeError):
        vars(_artifact())


def test_artifact_dunder_dict_access_and_replacement_fail() -> None:
    artifact = _artifact()
    with pytest.raises(AttributeError):
        _ = artifact.__dict__
    with pytest.raises(AttributeError):
        object.__setattr__(artifact, "__dict__", {"provider": True})
    with pytest.raises(AttributeError):
        object.__delattr__(artifact, "__dict__")


def test_weakref_slot_cannot_be_repurposed_as_proof_storage() -> None:
    artifact = _artifact()
    for value in (b"forged", _V10_PUBLIC_KEY, ("forged",)):
        with pytest.raises(AttributeError):
            object.__setattr__(artifact, "__weakref__", value)
    with pytest.raises(AttributeError):
        object.__delattr__(artifact, "__weakref__")
    assert artifact.signed_response_raw == _V05_SREP_RAW


def test_no_proof_field_is_a_writable_descriptor() -> None:
    for name in _EXPECTED_ARTIFACT_FIELDS:
        descriptor = getattr(RoughtimeV19SignedResponseVerification, name)
        assert type(descriptor) is property
        assert descriptor.fset is None, name
        assert descriptor.fdel is None, name


@pytest.mark.parametrize("field", _EXPECTED_ARTIFACT_FIELDS)
def test_setattr_rejected_for_every_field(field) -> None:
    artifact = _artifact()
    with pytest.raises(AttributeError):
        setattr(artifact, field, _V10_PUBLIC_KEY)


@pytest.mark.parametrize("field", _EXPECTED_ARTIFACT_FIELDS)
def test_delattr_rejected_for_every_field(field) -> None:
    artifact = _artifact()
    with pytest.raises(AttributeError):
        delattr(artifact, field)


@pytest.mark.parametrize("field", _EXPECTED_ARTIFACT_FIELDS)
def test_object_setattr_cannot_replace_any_proof_field(field) -> None:
    artifact = _artifact()
    before = getattr(artifact, field)
    with pytest.raises(AttributeError):
        object.__setattr__(artifact, field, _V10_PUBLIC_KEY)
    with pytest.raises(AttributeError):
        object.__delattr__(artifact, field)
    assert getattr(artifact, field) == before


@pytest.mark.parametrize("name", ["provider_id", "time_valid", "ready", "quorum_ok", "note"])
def test_arbitrary_public_state_cannot_be_added(name) -> None:
    artifact = _artifact()
    with pytest.raises(AttributeError):
        setattr(artifact, name, True)
    with pytest.raises(AttributeError):
        object.__setattr__(artifact, name, True)
    assert not hasattr(artifact, name)


@pytest.mark.parametrize("name", ["_cache", "_verified", "_trusted_root", "_reason"])
def test_arbitrary_private_state_cannot_be_added(name) -> None:
    artifact = _artifact()
    with pytest.raises(AttributeError):
        setattr(artifact, name, {"trusted": True})
    with pytest.raises(AttributeError):
        object.__setattr__(artifact, name, {"trusted": True})
    assert not hasattr(artifact, name)


def test_hash_is_stable_after_every_attempted_mutation() -> None:
    artifact = _artifact()
    before = hash(artifact)
    for name in (*_EXPECTED_ARTIFACT_FIELDS, "provider_id", "_cache", "__dict__"):
        with pytest.raises(AttributeError):
            setattr(artifact, name, b"forged")
        with pytest.raises(AttributeError):
            object.__setattr__(artifact, name, b"forged")
        with pytest.raises(AttributeError):
            delattr(artifact, name)
    assert hash(artifact) == before
    assert hash(artifact) == hash(_artifact())


def test_dictionary_key_and_set_membership_stay_stable() -> None:
    first = _artifact()
    second = _artifact()
    mapping = {first: "proof"}
    registry = {first}
    assert mapping[second] == "proof"
    assert second in registry
    with pytest.raises(AttributeError):
        object.__setattr__(second, "delegated_public_key", bytes(32))
    assert mapping[second] == "proof"
    assert second in registry
    assert len({first, second}) == 1


def test_equality_is_stable_and_strictly_type_bound() -> None:
    first = _artifact()
    second = _artifact()
    assert operator.eq(first, second) is True
    assert operator.ne(first, second) is False
    plain = _registered_state(first)
    assert operator.ne(first, plain) is True
    assert operator.ne(plain, first) is True
    assert operator.eq(first, plain) is False
    assert operator.ne(first, object()) is True


@pytest.mark.parametrize("impostor", ["tuple", "list", "dict"])
def test_no_builtin_container_can_impersonate_a_proof(impostor) -> None:
    artifact = _artifact()
    state = _registered_state(artifact)
    candidate = {
        "tuple": state,
        "list": list(state),
        "dict": dict(zip(_EXPECTED_ARTIFACT_FIELDS, state)),
    }[impostor]
    assert operator.eq(artifact, candidate) is False
    assert operator.ne(artifact, candidate) is True
    assert operator.eq(candidate, artifact) is False


def test_inequality_is_defined_explicitly_on_the_artifact() -> None:
    assert "__ne__" in vars(RoughtimeV19SignedResponseVerification)
    assert "__eq__" in vars(RoughtimeV19SignedResponseVerification)
    assert "__hash__" in vars(RoughtimeV19SignedResponseVerification)
    assert RoughtimeV19SignedResponseVerification.__hash__ is not None


@pytest.mark.parametrize("operation", ["lt", "le", "gt", "ge"])
def test_ordering_is_inapplicable(operation) -> None:
    with pytest.raises(TypeError):
        getattr(operator, operation)(_artifact(), _artifact())


@pytest.mark.parametrize("operand", [(), (1,), 2])
def test_concatenation_and_repetition_are_inapplicable(operand) -> None:
    artifact = _artifact()
    with pytest.raises(TypeError):
        _ = artifact + operand
    with pytest.raises(TypeError):
        _ = artifact * operand


_SEQUENCE_PROTOCOL_NAMES = (
    "__getitem__",
    "__setitem__",
    "__delitem__",
    "__iter__",
    "__next__",
    "__len__",
    "__contains__",
    "__reversed__",
    "__add__",
    "__mul__",
    "__rmul__",
    "__getnewargs__",
    "count",
    "index",
)


@pytest.mark.parametrize("name", _SEQUENCE_PROTOCOL_NAMES)
def test_sequence_protocol_is_absent_from_the_artifact(name) -> None:
    artifact = _artifact()
    assert not hasattr(RoughtimeV19SignedResponseVerification, name), name
    assert not hasattr(artifact, name), name


def test_sequence_operations_fail_without_exposing_proof_state() -> None:
    artifact = _artifact()
    for label, operation in (
        ("len", lambda obj: len(obj)),
        ("iter", lambda obj: iter(obj)),
        ("index", lambda obj: obj[0]),
        ("membership", lambda obj: _V05_SREP_RAW in obj),
        ("unpack", lambda obj: [*obj]),
    ):
        with pytest.raises(TypeError) as excinfo:
            operation(artifact)
        assert _V05_SREP_RAW.hex() not in str(excinfo.value), label


def test_copy_deepcopy_and_pickle_stay_valid_and_immutable() -> None:
    artifact = _artifact()
    clones = (
        copy.copy(artifact),
        copy.deepcopy(artifact),
        pickle.loads(pickle.dumps(artifact)),  # noqa: S301 - round-trips this module's own artifact only
    )
    for clone in clones:
        assert type(clone) is RoughtimeV19SignedResponseVerification
        assert clone == artifact
        assert hash(clone) == hash(artifact)
        assert not hasattr(clone, "__dict__")
        assert clone.signed_response_raw == _V05_SREP_RAW
        assert clone.response_signature == _V05_SIGNATURE
        with pytest.raises(AttributeError):
            object.__setattr__(clone, "signed_midpoint", 0)


def test_pickle_payload_carries_no_registry_state() -> None:
    artifact = _artifact()
    payload = pickle.dumps(artifact)
    assert b"_rebuild_signed_response_verification" in payload
    assert b"registry" not in payload
    assert b"proven_state" not in payload
    restored = pickle.loads(payload)  # noqa: S301 - round-trips this module's own artifact only
    assert restored == artifact


def test_pickle_rebuild_helper_rejects_malformed_state() -> None:
    from crypto_core.validation.roughtime_v19_signed_response_verification import (
        _rebuild_signed_response_verification,
    )

    state = _registered_state(_artifact())
    malformed = (
        None,
        (),
        state[:9],
        (*state, b"extra"),
        list(state),
        (b"forged", *state[1:]),
        (state[0], _V10_PUBLIC_KEY, *state[2:]),
        (*state[:2], _V10_PUBLIC_KEY, *state[3:]),
        (*state[:3], _V08_REENCODED_SREP, *state[4:]),
        (*state[:5], bytes(32), *state[6:]),
        (*state[:6], 0, *state[7:]),
        (*state[:9], (99,)),
        (bytearray(state[0]), *state[1:]),
    )
    for bad in malformed:
        with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
            _rebuild_signed_response_verification(bad)
        assert excinfo.value.reason is R.ARTIFACT_SIGNED_RESPONSE_VERIFICATION_INCONSISTENT
    assert _rebuild_signed_response_verification(state).signed_response_raw == _V05_SREP_RAW


def test_state_validator_rejects_foreign_and_malformed_state() -> None:
    from crypto_core.validation.roughtime_v19_signed_response_verification import (
        _ARTIFACT_INCONSISTENT,
        _validate_state_tuple,
    )

    genuine = _registered_state(_artifact())
    for bad in (None, (), [*genuine], genuine[:9], (*genuine, b"extra"), _hollow(RoughtimeV19ResponseSemantics)):
        with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
            _validate_state_tuple(bad, _ARTIFACT_INCONSISTENT)
        assert excinfo.value.reason is R.ARTIFACT_SIGNED_RESPONSE_VERIFICATION_INCONSISTENT
    _validate_state_tuple(genuine, _ARTIFACT_INCONSISTENT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("long_term_public_key", _V10_PUBLIC_KEY),
        ("delegated_public_key", _V10_PUBLIC_KEY),
        ("response_signature", bytes(64)),
        ("signed_response_raw", _V12_SREP_RAW),
        ("signed_root", bytes(32)),
        ("signed_midpoint", 0),
        ("signed_radius", 0),
        ("signed_version", 99),
        ("signed_versions", (99,)),
        ("response_raw", b""),
    ],
)
def test_altered_artifact_field_rejected(field, value) -> None:
    fields = _valid_artifact_fields()
    fields[field] = value
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        RoughtimeV19SignedResponseVerification(**fields)
    assert excinfo.value.reason is R.ARTIFACT_SIGNED_RESPONSE_VERIFICATION_INCONSISTENT


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("response_raw", None),
        ("long_term_public_key", bytearray(_V01_PUBLIC_KEY)),
        ("signed_midpoint", "150"),
        ("signed_radius", True),
        ("signed_versions", [1, 1073741825]),
        ("signed_version", 1.0),
    ],
)
def test_wrong_artifact_field_type_rejected(field, value) -> None:
    fields = _valid_artifact_fields()
    fields[field] = value
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        RoughtimeV19SignedResponseVerification(**fields)
    assert excinfo.value.reason is R.ARTIFACT_SIGNED_RESPONSE_VERIFICATION_INCONSISTENT


# ============================================================================================================
# Explicit unbound built-in base calls
# ============================================================================================================
_TUPLE_BASE_CALLS = (
    ("tuple.__getitem__", lambda obj: tuple.__getitem__(obj, 0)),
    ("tuple.__iter__", lambda obj: list(tuple.__iter__(obj))),
    ("tuple.__repr__", lambda obj: tuple.__repr__(obj)),
    ("tuple.__getnewargs__", lambda obj: tuple.__getnewargs__(obj)),
    ("tuple.__contains__", lambda obj: tuple.__contains__(obj, 1)),
    ("tuple.count", lambda obj: tuple.count(obj, 1)),
    ("tuple.index", lambda obj: tuple.index(obj, 1)),
    ("tuple.__add__", lambda obj: tuple.__add__(obj, ())),
    ("tuple.__hash__", lambda obj: tuple.__hash__(obj)),
    ("tuple.__len__", lambda obj: tuple.__len__(obj)),
)

_SECRET_MARKERS = (_V05_SREP_RAW, _V05_SIGNATURE, _V05_PUBLIC_KEY, _V01_PUBLIC_KEY)


def _assert_no_proof_state_in(value: object, label: str) -> None:
    rendered = repr(value)
    for marker in _SECRET_MARKERS:
        assert marker.hex() not in rendered, label
    assert "ROUGHTIM" not in rendered, label


@pytest.mark.parametrize("name,call", _TUPLE_BASE_CALLS, ids=lambda value: value if isinstance(value, str) else "")
@pytest.mark.parametrize("kind", ["genuine", "hollow"])
def test_unbound_tuple_base_calls_are_inapplicable_and_expose_nothing(name, call, kind) -> None:
    subject = _artifact() if kind == "genuine" else object.__new__(RoughtimeV19SignedResponseVerification)
    with pytest.raises(TypeError) as excinfo:
        call(subject)
    _assert_no_proof_state_in(str(excinfo.value), f"{kind}/{name}")


@pytest.mark.parametrize("base", [list, dict, bytes, bytearray, str, set, frozenset])
def test_other_builtin_base_calls_are_also_inapplicable(base) -> None:
    with pytest.raises(TypeError):
        base.__repr__(_artifact())


def test_object_base_calls_expose_no_proof_state() -> None:
    artifact = _artifact()
    hollow = object.__new__(RoughtimeV19SignedResponseVerification)
    for label, subject in (("genuine", artifact), ("hollow", hollow)):
        rendered = object.__repr__(subject)
        _assert_no_proof_state_in(rendered, f"object.__repr__/{label}")
        assert "RoughtimeV19SignedResponseVerification object at" in rendered
        assert type(object.__hash__(subject)) is int
    assert repr(artifact).startswith("RoughtimeV19SignedResponseVerification(response_raw=")
    with pytest.raises(RoughtimeV19SignedResponseVerificationError):
        repr(hollow)


# ============================================================================================================
# Registry identity, weakref binding, lifecycle and hollow rejection
# ============================================================================================================
def _closure_registry() -> dict:
    """Locate the closure-local registry for lifecycle assertions. Test-only implementation inspection.

    Explicitly OUTSIDE the supported trust boundary (Option A) - this path exists only to prove lifecycle
    cleanup and identity binding, and is deliberately not a documented or public API.
    """
    seen: list[dict] = []
    for cell in RoughtimeV19SignedResponseVerification.__hash__.__closure__ or ():
        try:
            content = cell.cell_contents
        except ValueError:  # pragma: no cover - empty cell
            continue
        if type(content) is dict:
            seen.append(content)
        if callable(content):
            for inner in getattr(content, "__closure__", None) or ():
                try:
                    nested = inner.cell_contents
                except ValueError:  # pragma: no cover - empty cell
                    continue
                if type(nested) is dict:
                    seen.append(nested)
    assert seen, "closure-local registry not reachable for lifecycle assertions"
    return seen[0]


def test_registry_is_not_reachable_through_the_module_namespace() -> None:
    import crypto_core.validation.roughtime_v19_signed_response_verification as module

    for name in dir(module):
        if name.startswith("__"):
            continue
        assert type(getattr(module, name)) is not dict, name


def test_registry_binds_exactly_one_entry_per_live_artifact() -> None:
    registry = _closure_registry()
    baseline = len(registry)
    first = _artifact()
    second = _artifact()
    assert len(registry) == baseline + 2
    assert id(first) in registry
    assert id(second) in registry
    reference, state = registry[id(first)]
    assert reference() is first
    assert type(state) is tuple
    assert len(state) == 10


def test_registry_entry_is_removed_when_the_artifact_dies() -> None:
    registry = _closure_registry()
    baseline = len(registry)
    artifact = _artifact()
    key = id(artifact)
    assert key in registry
    del artifact
    gc.collect()
    assert key not in registry
    assert len(registry) == baseline


def test_failed_construction_leaves_no_registry_entry() -> None:
    registry = _closure_registry()
    baseline = len(registry)
    fields = _valid_artifact_fields()
    fields["signed_midpoint"] = 0
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        RoughtimeV19SignedResponseVerification(**fields)
    assert excinfo.value.reason is R.ARTIFACT_SIGNED_RESPONSE_VERIFICATION_INCONSISTENT
    assert len(registry) == baseline


def test_hollow_instance_has_no_registry_entry() -> None:
    registry = _closure_registry()
    hollow = object.__new__(RoughtimeV19SignedResponseVerification)
    assert id(hollow) not in registry


def test_a_stale_or_mismatched_weakref_never_authenticates_another_object() -> None:
    registry = _closure_registry()
    genuine = _artifact()
    state = _registered_state(genuine)
    impostor = object.__new__(RoughtimeV19SignedResponseVerification)
    key = id(impostor)
    assert key not in registry
    registry[key] = (weakref.ref(genuine), state)
    try:
        for consume in (lambda obj: obj.response_raw, repr, hash, lambda obj: obj.__reduce__()):
            with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
                consume(impostor)
            assert excinfo.value.reason is R.ARTIFACT_SIGNED_RESPONSE_VERIFICATION_INCONSISTENT
    finally:
        registry.pop(key, None)
    assert genuine.signed_response_raw == _V05_SREP_RAW


def test_a_dead_weakref_entry_never_authenticates() -> None:
    registry = _closure_registry()
    state = _registered_state(_artifact())
    doomed = _artifact()
    reference = weakref.ref(doomed)
    del doomed
    gc.collect()
    assert reference() is None
    impostor = object.__new__(RoughtimeV19SignedResponseVerification)
    key = id(impostor)
    registry[key] = (reference, state)
    try:
        with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
            impostor.response_raw
        assert excinfo.value.reason is R.ARTIFACT_SIGNED_RESPONSE_VERIFICATION_INCONSISTENT
    finally:
        registry.pop(key, None)


def test_registry_lookup_never_invokes_artifact_equality_or_hash() -> None:
    registry = _closure_registry()
    _artifact()
    for key in registry:
        assert type(key) is int


_CONSUMPTION_SURFACES = (
    ("response_raw_property", lambda obj: obj.response_raw),
    ("long_term_key_property", lambda obj: obj.long_term_public_key),
    ("delegated_key_property", lambda obj: obj.delegated_public_key),
    ("signed_response_raw_property", lambda obj: obj.signed_response_raw),
    ("response_signature_property", lambda obj: obj.response_signature),
    ("signed_root_property", lambda obj: obj.signed_root),
    ("signed_midpoint_property", lambda obj: obj.signed_midpoint),
    ("signed_radius_property", lambda obj: obj.signed_radius),
    ("signed_version_property", lambda obj: obj.signed_version),
    ("signed_versions_property", lambda obj: obj.signed_versions),
    ("repr", repr),
    ("hash", hash),
    ("reduce", lambda obj: obj.__reduce__()),
    ("copy", copy.copy),
    ("deepcopy", copy.deepcopy),
    ("pickle", pickle.dumps),
)


@pytest.mark.parametrize(
    "surface,consume", _CONSUMPTION_SURFACES, ids=lambda value: value if isinstance(value, str) else ""
)
def test_hollow_instance_fails_closed_on_every_public_surface(surface, consume) -> None:
    hollow = object.__new__(RoughtimeV19SignedResponseVerification)
    with pytest.raises(RoughtimeV19SignedResponseVerificationError) as excinfo:
        consume(hollow)
    assert excinfo.value.reason is R.ARTIFACT_SIGNED_RESPONSE_VERIFICATION_INCONSISTENT, surface


def test_hollow_instance_never_equals_or_collides_with_a_genuine_proof() -> None:
    genuine = _artifact()
    hollow = object.__new__(RoughtimeV19SignedResponseVerification)
    for consume in (
        lambda: genuine == hollow,
        lambda: hollow == genuine,
        lambda: genuine != hollow,
        lambda: hollow != genuine,
        lambda: hollow in {genuine},
        lambda: {genuine: "proof"}[hollow],
    ):
        with pytest.raises(RoughtimeV19SignedResponseVerificationError):
            consume()


# ============================================================================================================
# Artifact sealing
# ============================================================================================================
_SEAL_LEDGER: list[str] = []


def _define_ordinary_subclass() -> type:
    class _Ordinary(RoughtimeV19SignedResponseVerification):
        pass

    return _Ordinary


def _define_new_override_subclass() -> type:
    class _NoValidation(RoughtimeV19SignedResponseVerification):
        def __new__(cls, **fields: object) -> object:
            _SEAL_LEDGER.append("__new__")
            return object.__new__(cls)

    return _NoValidation


def _define_getattribute_subclass() -> type:
    class _Hostile(RoughtimeV19SignedResponseVerification):
        def __getattribute__(self, name: str) -> object:
            _SEAL_LEDGER.append("__getattribute__")
            return object.__getattribute__(self, name)

    return _Hostile


def test_every_subclass_form_is_sealed() -> None:
    _SEAL_LEDGER.clear()
    for definer in (_define_ordinary_subclass, _define_new_override_subclass, _define_getattribute_subclass):
        with pytest.raises(TypeError) as excinfo:
            definer()
        assert type(excinfo.value) is TypeError
        assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE
    with pytest.raises(TypeError) as excinfo:
        type("_Dynamic", (RoughtimeV19SignedResponseVerification,), {})
    assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE
    assert _SEAL_LEDGER == []


# ============================================================================================================
# Error and profile contract
# ============================================================================================================
def test_profile_id_is_exact() -> None:
    assert ROUGHTIME_V19_SIGNED_RESPONSE_VERIFICATION_PROFILE_ID == _EXPECTED_PROFILE_ID


def test_reason_enum_is_exactly_six_members_in_order() -> None:
    assert tuple(member.value for member in R) == _EXPECTED_REASON_VALUES
    assert len(R) == 6


def test_error_str_is_reason_value_and_reason_is_exact() -> None:
    for member in R:
        error = RoughtimeV19SignedResponseVerificationError(member)
        assert str(error) == member.value
        assert error.reason is member


@pytest.mark.parametrize("bad", ["srep_signature_invalid", 0, None, object()])
def test_error_rejects_non_member_reason(bad) -> None:
    with pytest.raises(TypeError) as excinfo:
        RoughtimeV19SignedResponseVerificationError(bad)
    assert str(excinfo.value) == _EXPECTED_REASON_TYPE_MESSAGE


def test_error_rejects_hostile_value_property_before_reading_it() -> None:
    reads: list[str] = []

    class _HostileReason:
        @property
        def value(self) -> str:
            reads.append("value")
            return "srep_signature_invalid"

    with pytest.raises(TypeError):
        RoughtimeV19SignedResponseVerificationError(_HostileReason())
    assert reads == []


@pytest.mark.parametrize("locked", ["reason", "_reason", "args"])
def test_error_locked_attributes_block_ordinary_mutation(locked) -> None:
    error = RoughtimeV19SignedResponseVerificationError(R.WRONG_INPUT_TYPE)
    with pytest.raises(AttributeError):
        setattr(error, locked, "tampered")
    with pytest.raises(AttributeError):
        delattr(error, locked)


# ============================================================================================================
# Non-claim and forbidden-surface checks
# ============================================================================================================
def test_production_exports_exactly_five_public_symbols() -> None:
    exports: list[str] = []
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    exports = [element.value for element in node.value.elts]
    assert exports == [
        "ROUGHTIME_V19_SIGNED_RESPONSE_VERIFICATION_PROFILE_ID",
        "RoughtimeV19SignedResponseVerification",
        "RoughtimeV19SignedResponseVerificationError",
        "RoughtimeV19SignedResponseVerificationReason",
        "verify_roughtime_v19_signed_response",
    ]


def test_production_uses_no_isinstance() -> None:
    calls = {
        node.func.id
        for node in ast.walk(_production_tree())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "isinstance" not in calls


def test_production_uses_detached_verify_with_message_then_signature() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    assert "VerifyKey(public_key, encoder=RawEncoder).verify(transcript, signature)" in source


def test_production_uses_no_forbidden_backend_api() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "SigningKey",
        "crypto_sign_open",
        "crypto_sign_ed25519ph",
        "crypto_sign(",
        "to_curve25519",
        "SignedMessage",
        "SODIUM_INSTALL",
    ):
        assert forbidden not in source


def test_production_performs_no_inclusion_provider_or_readiness_work() -> None:
    """Executable surface only: docstrings may NAME these as non-claims, but no code may touch them."""
    tree = _production_tree()
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    identifiers = {token.lower() for token in attributes | names}
    for forbidden in (
        "server_key_id",
        "srv",
        "connector_ready_dialects",
        "mt4_verifier_profile_selected",
        "sha512",
        "verify_roughtime_v19_request_inclusion",
        "readiness_promoted",
        "quorum",
    ):
        assert forbidden not in identifiers


def test_production_reads_no_clock_or_randomness() -> None:
    modules: set[str] = set()
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
    for forbidden in ("time", "datetime", "random", "secrets", "os", "socket", "requests", "pathlib"):
        assert forbidden not in modules


def test_production_imports_only_the_pinned_backend_and_merged_layers() -> None:
    modules: set[str] = set()
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    assert modules == {
        "__future__",
        "enum",
        "weakref",
        "nacl.encoding",
        "nacl.exceptions",
        "nacl.signing",
        "crypto_core.validation.roughtime_v19_certificate_verification",
        "crypto_core.validation.roughtime_v19_response_semantics",
    }
