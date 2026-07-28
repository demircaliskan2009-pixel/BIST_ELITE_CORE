"""Deterministic contract tests for the Roughtime draft-19 CERT/delegation signature verifier (K5).

Vector provenance: every cryptographic vector below is copied verbatim from the accepted Class-C research
packet (MT4_RT19_SIGNATURE_VECTOR_ADMISSION_PASS, corpus V01-V25). Nothing is generated here, nothing is
paraphrased and no hex is elided. The packet's generator was cryptography/OpenSSL and its second verifier was
PyNaCl/libsodium, so the positive vectors are cross-backend by construction; `cryptography` is NOT a runtime
or test dependency and is never imported.

Small-order inventory provenance: the seven encodings are transcribed byte-for-byte from the immutable
vendored libsodium source of the pinned backend — pyca/pynacl tag 1.6.2,
src/libsodium/src/libsodium/crypto_core/ed25519/ref10/ed25519_ref10.c, function ge25519_has_small_order,
static table blacklist[][32], whose own COMPILER_ASSERT fixes the count at exactly seven. They are pinned
here independently of the production module so the module cannot prove its own inventory.

Response fixtures are built by TEST-ONLY encoders independent of the production decoders; they embed the
packet's exact DELE and CERT bytes verbatim so K2 preserves them unchanged.
"""

from __future__ import annotations

import ast
import copy
import gc
import importlib.metadata
import operator
import pickle
import weakref
from pathlib import Path

import pytest
from nacl.exceptions import BadSignatureError
from nacl.exceptions import ValueError as NaclValueError

from crypto_core.validation.roughtime_v19_certificate_verification import (
    ROUGHTIME_V19_CERTIFICATE_VERIFICATION_PROFILE_ID,
    RoughtimeV19CertificateVerification,
    RoughtimeV19CertificateVerificationError,
    RoughtimeV19CertificateVerificationReason,
    verify_roughtime_v19_certificate,
)
from crypto_core.validation.roughtime_v19_response_semantics import (
    RoughtimeV19CertificateSemantics,
    RoughtimeV19DelegationSemantics,
    RoughtimeV19ResponseSemantics,
    parse_roughtime_v19_response,
)

R = RoughtimeV19CertificateVerificationReason

# --- Independently pinned identity constants --------------------------------------------------------------
_EXPECTED_PROFILE_ID = "roughtime-v19-certificate-verification-bounded-k5.v1"
_EXPECTED_SEAL_MESSAGE = "RoughtimeV19CertificateVerification is a sealed artifact type and cannot be subclassed"
_EXPECTED_REASON_TYPE_MESSAGE = (
    "RoughtimeV19CertificateVerificationError requires a RoughtimeV19CertificateVerificationReason member"
)
_EXPECTED_REASON_VALUES = (
    "wrong_input_type",
    "input_artifact_inconsistent",
    "long_term_public_key_invalid",
    "cert_signature_invalid",
    "crypto_backend_failure",
    "artifact_certificate_verification_inconsistent",
)
_EXPECTED_ARTIFACT_FIELDS = (
    "response_raw",
    "long_term_public_key",
    "certificate_raw",
    "certificate_signature",
    "delegation_raw",
    "delegated_public_key",
    "min_time",
    "max_time",
)
_FORBIDDEN_FIELD_TOKENS = (
    "verified",
    "authentic",
    "provider",
    "ready",
    "backend",
    "version",
    "provenance",
    "valid",
)

# --- Normative transcript (packet SRC-RT19-CERT) ----------------------------------------------------------
_CERT_CONTEXT = b"RoughTime v1 delegation signature\x00"
_CERT_CONTEXT_HEX = "526f75676854696d652076312064656c65676174696f6e207369676e617475726500"
_CERT_CONTEXT_LENGTH = 34

# --- Accepted packet vectors (verbatim) -------------------------------------------------------------------
# V01_CERT_CONTEXT_CORRECT — EXPECTED_RESULT ACCEPT
_V01_MESSAGE_HEX = (
    "526f75676854696d652076312064656c65676174696f6e207369676e617475726500040000002000000028000000300000005055"
    "424b4d494e544d4158545a5a5a5a29acbae141bccaf0b22e1a94d34d0bc7361e526d0bfe12c89794bc9322966dd7640000000000"
    "0000c800000000000000a0a1a2a3"
)
_V01_PUBLIC_KEY_HEX = "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8"
_V01_SIGNATURE_HEX = (
    "92c97ef4e509f01897fce1a4f71cf2375d8d5bbdbe4369bd6bf324ac1a235a9c752f981268424ce0b8feb48f55993b302adadb37"
    "12d02c848b1b447c4bbbf301"
)
_V01_DELE_RAW_HEX = (
    "040000002000000028000000300000005055424b4d494e544d4158545a5a5a5a29acbae141bccaf0b22e1a94d34d0bc7361e526d"
    "0bfe12c89794bc9322966dd76400000000000000c800000000000000a0a1a2a3"
)
_V01_MINT = 100
_V01_MAXT = 200

# V02_CERT_WRONG_CONTEXT — one ASCII case bit differs ("Signature" instead of "signature")
_V02_MESSAGE_HEX = (
    "526f75676854696d652076312064656c65676174696f6e205369676e617475726500040000002000000028000000300000005055"
    "424b4d494e544d4158545a5a5a5a29acbae141bccaf0b22e1a94d34d0bc7361e526d0bfe12c89794bc9322966dd7640000000000"
    "0000c800000000000000a0a1a2a3"
)

# V03_CERT_MISSING_NUL — exactly the trailing NUL omitted, 117 bytes
_V03_MESSAGE_HEX = (
    "526f75676854696d652076312064656c65676174696f6e207369676e6174757265040000002000000028000000300000005055424b"
    "4d494e544d4158545a5a5a5a29acbae141bccaf0b22e1a94d34d0bc7361e526d0bfe12c89794bc9322966dd76400000000000000c8"
    "00000000000000a0a1a2a3"
)

# V04_CERT_REENCODED_DELE — re-encoding omits the preserved ZZZZ extension (84 exact -> 72 re-encoded)
_V04_PUBLIC_KEY_HEX = "2543b92ff1095511476adc8369db6ddc933665a11978dda1404ee1066ca9559d"
_V04_SIGNATURE_HEX = (
    "58bd0aa70ff8b16e59c1d24dea91fb4d2c0912c4539c53f06f4e74a8f6c4695818f4bf1826e22d48c5bd024377c14739d1c81c92"
    "e6b25dbf26f48847dc5aa901"
)
_V04_REENCODED_DELE_HEX = (
    "0300000020000000280000005055424b4d494e544d41585429acbae141bccaf0b22e1a94d34d0bc7361e526d0bfe12c89794bc93"
    "22966dd76400000000000000c800000000000000"
)

# V09_WRONG_LONG_TERM_KEY — correct signature presented under a different long-term key
_V09_PUBLIC_KEY_HEX = "cd14b37f956e953194ff7fb73b3d81dcc561d61a7538094b7c3e1a643ee5f3aa"

# V11_CERT_ONE_BIT_MUTATION — final extension byte bit0 flipped (a3 -> a2)
_V11_DELE_RAW_HEX = (
    "040000002000000028000000300000005055424b4d494e544d4158545a5a5a5a29acbae141bccaf0b22e1a94d34d0bc7361e526d"
    "0bfe12c89794bc9322966dd76400000000000000c800000000000000a0a1a2a2"
)

# V13_PUBLIC_KEY_LENGTH_31 / V14_SIGNATURE_LENGTH_63
_V13_PUBLIC_KEY_HEX = "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531"
_V14_SIGNATURE_HEX = (
    "92c97ef4e509f01897fce1a4f71cf2375d8d5bbdbe4369bd6bf324ac1a235a9c752f981268424ce0b8feb48f55993b302adadb37"
    "12d02c848b1b447c4bbbf3"
)

# V15_SCALAR_S_EQUAL_L — R retained, S set to exactly the group order L
_V15_SIGNATURE_HEX = (
    "92c97ef4e509f01897fce1a4f71cf2375d8d5bbdbe4369bd6bf324ac1a235a9cedd3f55c1a631258d69cf7a2def9de1400000000"
    "000000000000000000000010"
)

# V16_NONCANONICAL_R — R encodes y=p; S retained
_V16_SIGNATURE_HEX = (
    "edffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f752f981268424ce0b8feb48f55993b302adadb37"
    "12d02c848b1b447c4bbbf301"
)

# V17_NONCANONICAL_A — public key A encodes y=p
_V17_PUBLIC_KEY_HEX = "edffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f"

# V18_IDENTITY_PUBLIC_KEY / V19_ORDER8_PUBLIC_KEY — REJECT_BY_CONTROLLER_HARDENING
_V18_PUBLIC_KEY_HEX = "0100000000000000000000000000000000000000000000000000000000000000"
_V19_PUBLIC_KEY_HEX = "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05"
_V18_V19_SIGNATURE_HEX = (
    "5866666666666666666666666666666666666666666666666666666666666666"
    "0100000000000000000000000000000000000000000000000000000000000000"
)

_V01_MESSAGE = bytes.fromhex(_V01_MESSAGE_HEX)
_V01_PUBLIC_KEY = bytes.fromhex(_V01_PUBLIC_KEY_HEX)
_V01_SIGNATURE = bytes.fromhex(_V01_SIGNATURE_HEX)
_V01_DELE_RAW = bytes.fromhex(_V01_DELE_RAW_HEX)
_V04_PUBLIC_KEY = bytes.fromhex(_V04_PUBLIC_KEY_HEX)
_V04_SIGNATURE = bytes.fromhex(_V04_SIGNATURE_HEX)
_V04_REENCODED_DELE = bytes.fromhex(_V04_REENCODED_DELE_HEX)
_V09_PUBLIC_KEY = bytes.fromhex(_V09_PUBLIC_KEY_HEX)
_V11_DELE_RAW = bytes.fromhex(_V11_DELE_RAW_HEX)
_V13_PUBLIC_KEY = bytes.fromhex(_V13_PUBLIC_KEY_HEX)
_V14_SIGNATURE = bytes.fromhex(_V14_SIGNATURE_HEX)
_V15_SIGNATURE = bytes.fromhex(_V15_SIGNATURE_HEX)
_V16_SIGNATURE = bytes.fromhex(_V16_SIGNATURE_HEX)
_V17_PUBLIC_KEY = bytes.fromhex(_V17_PUBLIC_KEY_HEX)
_V18_PUBLIC_KEY = bytes.fromhex(_V18_PUBLIC_KEY_HEX)
_V19_PUBLIC_KEY = bytes.fromhex(_V19_PUBLIC_KEY_HEX)
_V18_V19_SIGNATURE = bytes.fromhex(_V18_V19_SIGNATURE_HEX)

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


# --- Test-only encoders (independent of production) -------------------------------------------------------
def _le(tag: bytes) -> int:
    return int.from_bytes(tag, "little")


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "little")


def _u64(value: int) -> bytes:
    return int(value).to_bytes(8, "little")


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
    signature: bytes = _V01_SIGNATURE,
    dele: bytes = _V01_DELE_RAW,
    midpoint: int = 150,
) -> bytes:
    srep = _encode_message(
        [
            (_TAG_VER, _u32(1)),
            (_TAG_RADI, _u32(3)),
            (_TAG_MIDP, _u64(midpoint)),
            (_TAG_VERS, _u32(1) + _u32(0x40000001)),
            (_TAG_ROOT, bytes(32)),
        ]
    )
    outer = _encode_message(
        [
            (_TAG_SIG, bytes(64)),
            (_TAG_NONC, bytes(32)),
            (_TAG_TYPE, _u32(1)),
            (_TAG_PATH, b""),
            (_TAG_SREP, srep),
            (_TAG_CERT, _cert_raw(signature=signature, dele=dele)),
            (_TAG_INDX, _u32(0)),
        ]
    )
    return _encode_packet(outer)


def _dele_with_times(min_time: int, max_time: int) -> bytes:
    """Rebuild a DELE carrying the packet's exact PUBK but different MINT/MAXT, for interval coverage."""
    pubk = _V01_DELE_RAW[32:64]
    return _encode_message(
        [
            (b"PUBK", pubk),
            (b"MINT", _u64(min_time)),
            (b"MAXT", _u64(max_time)),
            (b"ZZZZ", b"\xa0\xa1\xa2\xa3"),
        ]
    )


def _response(**kwargs) -> RoughtimeV19ResponseSemantics:
    return parse_roughtime_v19_response(_response_packet(**kwargs))


def _hollow(cls, **fields):
    obj = object.__new__(cls)
    for name, value in fields.items():
        object.__setattr__(obj, name, value)
    return obj


def _valid_artifact_fields() -> dict:
    response = _response()
    return {
        "response_raw": response.raw,
        "long_term_public_key": _V01_PUBLIC_KEY,
        "certificate_raw": response.certificate.raw,
        "certificate_signature": _V01_SIGNATURE,
        "delegation_raw": _V01_DELE_RAW,
        "delegated_public_key": response.certificate.delegation.pubk,
        "min_time": _V01_MINT,
        "max_time": _V01_MAXT,
    }


_PRODUCTION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "crypto_core"
    / "validation"
    / "roughtime_v19_certificate_verification.py"
)


def _production_tree() -> ast.Module:
    return ast.parse(_PRODUCTION_PATH.read_text(encoding="utf-8"))


# ============================================================================================================
# Dependency contract
# ============================================================================================================
def test_pynacl_pinned_version_is_exactly_1_6_2() -> None:
    assert importlib.metadata.version("PyNaCl") == "1.6.2"


def test_pynacl_resolves_and_native_backend_loads() -> None:
    import nacl.signing

    assert nacl.signing.VerifyKey is not None


def test_pyproject_pins_pynacl_exactly_once() -> None:
    text = (_PRODUCTION_PATH.parents[3] / "pyproject.toml").read_text(encoding="utf-8")
    assert text.count("PyNaCl==1.6.2") == 1
    assert "pynacl>=" not in text.lower()
    assert "cryptography" not in text.lower()


def test_requirements_txt_pins_pynacl_exactly_once() -> None:
    text = (_PRODUCTION_PATH.parents[3] / "requirements.txt").read_text(encoding="utf-8")
    assert text.count("PyNaCl==1.6.2") == 1
    assert "pynacl>=" not in text.lower()
    assert "cryptography" not in text.lower()


def test_requirements_dev_still_includes_requirements_so_ci_reaches_the_pin() -> None:
    text = (_PRODUCTION_PATH.parents[3] / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "-r requirements.txt" in text
    assert "PyNaCl" not in text


def test_no_lockfile_or_extra_dependency_file_added() -> None:
    root = _PRODUCTION_PATH.parents[3]
    for name in ("poetry.lock", "requirements.lock", "uv.lock", "Pipfile.lock", "requirements-crypto.txt"):
        assert not (root / name).exists()


def test_production_imports_no_cryptography_and_only_the_pinned_backend() -> None:
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
        "crypto_core.validation.roughtime_v19_response_semantics",
    }


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


def test_production_uses_detached_verify_with_message_then_signature() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    assert "VerifyKey(public_key, encoder=RawEncoder).verify(transcript, signature)" in source


# ============================================================================================================
# Normative transcript
# ============================================================================================================
def test_cert_context_is_exact_with_trailing_nul() -> None:
    assert _CERT_CONTEXT.hex() == _CERT_CONTEXT_HEX
    assert len(_CERT_CONTEXT) == _CERT_CONTEXT_LENGTH
    assert _CERT_CONTEXT.endswith(b"\x00")


def test_v01_transcript_is_context_plus_exact_dele() -> None:
    assert _V01_MESSAGE == _CERT_CONTEXT + _V01_DELE_RAW
    assert len(_V01_MESSAGE) == 118
    assert len(_V01_DELE_RAW) == 84


def test_production_pins_the_exact_context_constant() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    assert 'b"RoughTime v1 delegation signature\\x00"' in source


# ============================================================================================================
# Positive coverage
# ============================================================================================================
def test_v01_cert_context_correct_verifies() -> None:
    artifact = verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY)
    assert artifact.long_term_public_key == _V01_PUBLIC_KEY
    assert artifact.certificate_signature == _V01_SIGNATURE
    assert artifact.delegation_raw == _V01_DELE_RAW
    assert artifact.min_time == _V01_MINT
    assert artifact.max_time == _V01_MAXT


def test_verifier_artifact_carries_exact_k2_derived_values() -> None:
    response = _response()
    artifact = verify_roughtime_v19_certificate(response, _V01_PUBLIC_KEY)
    assert artifact.response_raw == response.raw
    assert artifact.certificate_raw == response.certificate.raw
    assert artifact.delegated_public_key == response.certificate.delegation.pubk
    assert artifact.delegation_raw == response.certificate.delegation.raw


def test_exact_preserved_dele_includes_the_unknown_extension() -> None:
    response = _response()
    assert response.certificate.delegation.raw.endswith(b"\xa0\xa1\xa2\xa3")
    assert len(response.certificate.delegation.extensions) == 1


def test_direct_artifact_construction_succeeds() -> None:
    artifact = RoughtimeV19CertificateVerification(**_valid_artifact_fields())
    assert artifact.delegation_raw == _V01_DELE_RAW


def test_equality_and_hashing_are_deterministic() -> None:
    first = verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY)
    second = verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY)
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1


@pytest.mark.parametrize("midpoint", [100, 150, 200])
def test_v20_v22_interval_boundaries_still_verify(midpoint) -> None:
    """V20-V22: MIDP sits outside the signed DELE, so boundary midpoints never disturb the CERT signature."""
    response = _response(midpoint=midpoint)
    assert response.signed_response.midpoint_seconds == midpoint
    artifact = verify_roughtime_v19_certificate(response, _V01_PUBLIC_KEY)
    assert artifact.min_time == _V01_MINT
    assert artifact.max_time == _V01_MAXT


def test_rebuilt_dele_with_the_signed_times_is_byte_identical() -> None:
    """The independent test encoder reproduces the packet's exact DELE, so the signature still validates."""
    rebuilt = _dele_with_times(_V01_MINT, _V01_MAXT)
    assert rebuilt == _V01_DELE_RAW
    verify_roughtime_v19_certificate(_response(dele=rebuilt), _V01_PUBLIC_KEY)


def test_changed_delegation_interval_breaks_the_signature() -> None:
    """MINT/MAXT are inside the signed DELE, so altering them must invalidate the CERT signature."""
    dele = _dele_with_times(150, 150)
    assert dele != _V01_DELE_RAW
    response = parse_roughtime_v19_response(_response_packet(dele=dele, midpoint=150))
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(response, _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID


@pytest.mark.parametrize(("min_time", "midpoint", "max_time"), [(100, 50, 200), (100, 250, 200), (200, 150, 100)])
def test_k2_rejects_invalid_intervals_before_k5(min_time, midpoint, max_time) -> None:
    """V23-V25: K2's structural interval rules fire at parse time, so K5 never sees the response."""
    dele = _dele_with_times(min_time, max_time)
    with pytest.raises(Exception) as excinfo:
        parse_roughtime_v19_response(_response_packet(dele=dele, midpoint=midpoint))
    assert type(excinfo.value) is not RoughtimeV19CertificateVerificationError


# ============================================================================================================
# Negative signature coverage (packet vectors)
# ============================================================================================================
def _backend_rejects(message: bytes, public_key: bytes, signature: bytes) -> bool:
    """Ask the pinned backend directly whether a transcript fails, independently of the K5 verifier."""
    from nacl.encoding import RawEncoder
    from nacl.signing import VerifyKey

    try:
        VerifyKey(public_key, encoder=RawEncoder).verify(message, signature)
    except BadSignatureError:
        return True
    return False


def test_v02_wrong_context_transcript_does_not_verify() -> None:
    """V02 flips one ASCII case bit in the context; the verifier's pinned context can never produce it."""
    wrong = bytes.fromhex(_V02_MESSAGE_HEX)
    assert wrong != _V01_MESSAGE
    assert wrong[:_CERT_CONTEXT_LENGTH] != _CERT_CONTEXT
    assert wrong[_CERT_CONTEXT_LENGTH:] == _V01_DELE_RAW
    assert _backend_rejects(wrong, _V01_PUBLIC_KEY, _V01_SIGNATURE)
    assert not _backend_rejects(_V01_MESSAGE, _V01_PUBLIC_KEY, _V01_SIGNATURE)


def test_v03_missing_trailing_nul_transcript_does_not_verify() -> None:
    """V03 omits exactly the trailing NUL, proving the NUL is load-bearing in the signed input."""
    missing = bytes.fromhex(_V03_MESSAGE_HEX)
    assert len(missing) == 117
    assert missing == b"RoughTime v1 delegation signature" + _V01_DELE_RAW
    assert _backend_rejects(missing, _V01_PUBLIC_KEY, _V01_SIGNATURE)


def test_v04_reencoded_dele_rejected() -> None:
    """Re-encoding drops the preserved ZZZZ extension, so the signature over the exact bytes fails."""
    assert len(_V04_REENCODED_DELE) == 72
    response = _response(signature=_V04_SIGNATURE, dele=_V04_REENCODED_DELE)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(response, _V04_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID


def test_v04_reverse_generator_positive_verifies_through_production() -> None:
    """V04 as a POSITIVE: cross-backend in the opposite direction to V01.

    V01 was generated by cryptography/OpenSSL and cross-verified by PyNaCl/libsodium. V04's packet record
    states GENERATOR_IMPLEMENTATION PyNaCl==1.6.2 with the base exact transcript "cross-verified positive",
    so verifying V04's signature over the EXACT preserved 84-byte DELE exercises the reverse generator
    direction: signed by libsodium, verified through production K5. Without this the suite only ever proved
    the OpenSSL-signed direction, and a transcript defect that happened to be symmetric could survive.

    The re-encoded-DELE negative above is retained separately and uses the same key and signature.
    """
    assert _V04_PUBLIC_KEY != _V01_PUBLIC_KEY
    assert _V04_SIGNATURE != _V01_SIGNATURE
    response = _response(signature=_V04_SIGNATURE, dele=_V01_DELE_RAW)
    artifact = verify_roughtime_v19_certificate(response, _V04_PUBLIC_KEY)
    assert artifact.long_term_public_key == _V04_PUBLIC_KEY
    assert artifact.certificate_signature == _V04_SIGNATURE
    assert artifact.delegation_raw == _V01_DELE_RAW
    assert len(artifact.delegation_raw) == 84
    assert artifact.min_time == _V01_MINT
    assert artifact.max_time == _V01_MAXT


def test_v04_positive_and_negative_differ_only_by_the_presented_dele() -> None:
    """Pins WHY the pair is meaningful: identical key and signature, only the DELE bytes differ."""
    assert len(_V01_DELE_RAW) == 84
    assert len(_V04_REENCODED_DELE) == 72
    assert _V04_REENCODED_DELE != _V01_DELE_RAW
    verify_roughtime_v19_certificate(_response(signature=_V04_SIGNATURE, dele=_V01_DELE_RAW), _V04_PUBLIC_KEY)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(signature=_V04_SIGNATURE, dele=_V04_REENCODED_DELE), _V04_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID


def test_v09_wrong_long_term_key_rejected() -> None:
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(), _V09_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID


def test_v11_one_bit_dele_mutation_rejected() -> None:
    assert _V11_DELE_RAW != _V01_DELE_RAW
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(dele=_V11_DELE_RAW), _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID


def test_v15_scalar_s_equal_to_group_order_rejected() -> None:
    assert int.from_bytes(_V15_SIGNATURE[32:], "little") == _GROUP_ORDER
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(signature=_V15_SIGNATURE), _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID


def test_scalar_s_above_group_order_rejected() -> None:
    signature = _V01_SIGNATURE[:32] + (_GROUP_ORDER + 1).to_bytes(32, "little")
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(signature=signature), _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID


def test_v16_noncanonical_r_rejected() -> None:
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(signature=_V16_SIGNATURE), _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID


# ============================================================================================================
# Long-term public-key policy
# ============================================================================================================
@pytest.mark.parametrize(
    ("label", "key"),
    [
        ("V13_length_31", _V13_PUBLIC_KEY),
        ("length_33", _V01_PUBLIC_KEY + b"\x00"),
        ("empty", b""),
        ("V17_noncanonical_a", _V17_PUBLIC_KEY),
        ("V18_identity", _V18_PUBLIC_KEY),
        ("V19_order8", _V19_PUBLIC_KEY),
        ("all_zero", bytes(32)),
    ],
)
def test_invalid_long_term_public_key_rejected(label, key) -> None:
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(), key)
    assert excinfo.value.reason is R.LONG_TERM_PUBLIC_KEY_INVALID, label


@pytest.mark.parametrize("index", range(_SMALL_ORDER_COUNT))
def test_every_small_order_encoding_rejected_as_public_key(index) -> None:
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(), _SMALL_ORDER_ENCODINGS[index])
    assert excinfo.value.reason is R.LONG_TERM_PUBLIC_KEY_INVALID


@pytest.mark.parametrize("index", range(_SMALL_ORDER_COUNT))
def test_every_small_order_encoding_rejected_as_signature_r(index) -> None:
    signature = _SMALL_ORDER_ENCODINGS[index] + _V01_SIGNATURE[32:]
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(signature=signature), _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID


# --- Sign-bit-masked small-order coverage -----------------------------------------------------------------
# libsodium (and therefore production `_is_small_order`) compares bytes 0..30 verbatim and byte 31 with the
# sign bit masked off, so toggling byte 31's high bit must NOT let a small-order point through. Toggling that
# bit never changes canonicality either, because `_is_canonical_point` masks the same bit before comparing to
# p - so these variants genuinely exercise the masked small-order comparison.
def _sign_bit_toggled(encoding: bytes) -> bytes:
    return encoding[:31] + bytes((encoding[31] ^ 0x80,))


_SIGN_BIT_TOGGLED_SMALL_ORDER = tuple(_sign_bit_toggled(entry) for entry in _SMALL_ORDER_ENCODINGS)

# Entries 5 and 6 encode y = p and y = p + 1, which are NON-canonical; the canonicality gate fires on those
# before the small-order gate is reached. Recorded explicitly so the two rejection causes stay distinguishable.
_CANONICAL_SMALL_ORDER_INDEXES = (0, 1, 2, 3, 4)
_NONCANONICAL_SMALL_ORDER_INDEXES = (5, 6)


def test_sign_bit_toggled_variants_are_distinct_and_well_formed() -> None:
    assert len(_SIGN_BIT_TOGGLED_SMALL_ORDER) == _SMALL_ORDER_COUNT
    for original, toggled in zip(_SMALL_ORDER_ENCODINGS, _SIGN_BIT_TOGGLED_SMALL_ORDER):
        assert toggled != original
        assert len(toggled) == 32
        assert toggled[:31] == original[:31]
        assert toggled[31] == original[31] ^ 0x80
        assert toggled not in _SMALL_ORDER_ENCODINGS


@pytest.mark.parametrize("index", range(_SMALL_ORDER_COUNT))
def test_sign_bit_toggled_small_order_rejected_as_public_key(index) -> None:
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(), _SIGN_BIT_TOGGLED_SMALL_ORDER[index])
    assert excinfo.value.reason is R.LONG_TERM_PUBLIC_KEY_INVALID, index


@pytest.mark.parametrize("index", range(_SMALL_ORDER_COUNT))
def test_sign_bit_toggled_small_order_rejected_as_signature_r(index) -> None:
    signature = _SIGN_BIT_TOGGLED_SMALL_ORDER[index] + _V01_SIGNATURE[32:]
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(signature=signature), _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID, index


def test_byte_31_masking_in_the_small_order_policy_is_pinned_directly() -> None:
    """White-box: pins the masking rule itself, independently of which gate fires first end-to-end.

    Without this, deleting the `& 0x7F` mask from `_is_small_order` could still leave every end-to-end test
    green, because the canonicality gate happens to reject the two non-canonical entries anyway.
    """
    from crypto_core.validation.roughtime_v19_certificate_verification import (
        _is_canonical_point,
        _is_small_order,
    )

    for index, (original, toggled) in enumerate(zip(_SMALL_ORDER_ENCODINGS, _SIGN_BIT_TOGGLED_SMALL_ORDER)):
        assert _is_small_order(original) is True, index
        assert _is_small_order(toggled) is True, index
        assert _is_canonical_point(original) is _is_canonical_point(toggled), index
    for index in _CANONICAL_SMALL_ORDER_INDEXES:
        assert _is_canonical_point(_SMALL_ORDER_ENCODINGS[index]) is True, index
        assert _is_canonical_point(_SIGN_BIT_TOGGLED_SMALL_ORDER[index]) is True, index
    for index in _NONCANONICAL_SMALL_ORDER_INDEXES:
        assert _is_canonical_point(_SMALL_ORDER_ENCODINGS[index]) is False, index
        assert _is_canonical_point(_SIGN_BIT_TOGGLED_SMALL_ORDER[index]) is False, index


def test_repository_policy_rejects_scalar_s_at_or_above_l_independently_of_the_backend() -> None:
    """White-box: libsodium also rejects a non-canonical S, so this pins OUR layer, not the backend's.

    Without a direct assertion the private scalar bound could be deleted and every end-to-end test would still
    pass on the backend's own check, silently removing the repository's defence-in-depth guarantee.
    """
    from crypto_core.validation.roughtime_v19_certificate_verification import _signature_rejected

    canonical_r = _V01_SIGNATURE[:32]
    assert _signature_rejected(canonical_r + _GROUP_ORDER.to_bytes(32, "little")) is True
    assert _signature_rejected(canonical_r + (_GROUP_ORDER + 1).to_bytes(32, "little")) is True
    assert _signature_rejected(canonical_r + (_GROUP_ORDER - 1).to_bytes(32, "little")) is False
    assert _signature_rejected(_V01_SIGNATURE) is False


def test_repository_policy_rejects_noncanonical_points_independently_of_the_backend() -> None:
    """White-box: uses y = p + 2, which is non-canonical yet NOT in the small-order inventory."""
    from crypto_core.validation.roughtime_v19_certificate_verification import (
        _public_key_rejected,
        _signature_rejected,
    )

    field_prime = (1 << 255) - 19
    non_canonical = (field_prime + 2).to_bytes(32, "little")
    assert non_canonical not in _SMALL_ORDER_ENCODINGS
    assert _public_key_rejected(non_canonical) is True
    assert _signature_rejected(non_canonical + _V01_SIGNATURE[32:]) is True
    assert _public_key_rejected(_V01_PUBLIC_KEY) is False


def test_hardening_constants_are_the_exact_rfc8032_values() -> None:
    from crypto_core.validation.roughtime_v19_certificate_verification import (
        _FIELD_PRIME,
    )
    from crypto_core.validation.roughtime_v19_certificate_verification import (
        _GROUP_ORDER as _PRODUCTION_L,
    )

    assert _FIELD_PRIME == (1 << 255) - 19
    assert _PRODUCTION_L == _GROUP_ORDER
    assert _PRODUCTION_L == 7237005577332262213973186563042994240857116359379907606001950938285454250989


def test_production_small_order_inventory_exactly_equals_the_pinned_oracle() -> None:
    """EXACT equality against the independently pinned tuple, not presence in the production source text.

    A containment check ("each pinned hex appears somewhere in the file") is a one-way oracle: it cannot detect
    an EXTRA production entry, a reordering, or a duplicate, and it lets the production source participate in
    proving its own inventory. This imports the live production object and compares it byte-for-byte, so the
    test file's pinned tuple is the sole authority.
    """
    from crypto_core.validation.roughtime_v19_certificate_verification import (
        _SMALL_ORDER_ENCODINGS as production_inventory,
    )

    assert type(production_inventory) is tuple
    assert len(production_inventory) == _SMALL_ORDER_COUNT == 7
    assert len(_SMALL_ORDER_ENCODINGS) == _SMALL_ORDER_COUNT
    for entry in production_inventory:
        assert type(entry) is bytes
        assert len(entry) == 32
    assert production_inventory == _SMALL_ORDER_ENCODINGS
    for index in range(_SMALL_ORDER_COUNT):
        assert production_inventory[index] == _SMALL_ORDER_ENCODINGS[index], index
    assert len(set(production_inventory)) == _SMALL_ORDER_COUNT
    assert set(production_inventory) == set(_SMALL_ORDER_ENCODINGS)


@pytest.mark.parametrize("extra", [bytes(32), bytes.fromhex("02" * 32)])
def test_an_extra_production_inventory_entry_would_break_exact_equality(extra) -> None:
    """Guards the oracle itself: an inventory with one entry added/removed must not compare equal."""
    from crypto_core.validation.roughtime_v19_certificate_verification import (
        _SMALL_ORDER_ENCODINGS as production_inventory,
    )

    assert (*production_inventory, extra) != _SMALL_ORDER_ENCODINGS
    assert production_inventory[:-1] != _SMALL_ORDER_ENCODINGS
    assert tuple(reversed(production_inventory)) != _SMALL_ORDER_ENCODINGS


def test_small_order_inventory_provenance_is_documented() -> None:
    """Provenance comments only - deliberately NOT the inventory oracle (see the exact-equality test above)."""
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    assert "ed25519_ref10.c" in source
    assert "1.6.2" in source
    assert "ge25519_has_small_order" in source


def test_v18_and_v19_are_inside_the_pinned_inventory() -> None:
    assert _V18_PUBLIC_KEY in _SMALL_ORDER_ENCODINGS
    assert _V19_PUBLIC_KEY in _SMALL_ORDER_ENCODINGS


@pytest.mark.parametrize("public_key", [_V18_PUBLIC_KEY, _V19_PUBLIC_KEY])
def test_v18_v19_exact_paired_signature_rejected_by_controller_hardening(public_key) -> None:
    """The packet pairs these weak keys with an equation-valid signature; hardening must reject them anyway."""
    assert len(_V18_V19_SIGNATURE) == 64
    point_r = _V18_V19_SIGNATURE[:32]
    assert point_r not in _SMALL_ORDER_ENCODINGS
    assert int.from_bytes(_V18_V19_SIGNATURE[32:], "little") < _GROUP_ORDER
    response = _response(signature=_V18_V19_SIGNATURE)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(response, public_key)
    assert excinfo.value.reason is R.LONG_TERM_PUBLIC_KEY_INVALID


def test_v14_short_signature_is_rejected_at_the_k2_boundary() -> None:
    """A 63-byte CERT SIG cannot survive K2's exact length rule, so it closes as an inconsistent input."""
    assert len(_V14_SIGNATURE) == 63
    raw = _response_packet(signature=_V14_SIGNATURE)
    hollow = _hollow(RoughtimeV19ResponseSemantics, raw=raw)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(hollow, _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


# ============================================================================================================
# Input trust boundary
# ============================================================================================================
_HOSTILE_ACCESS: list[str] = []


def _define_hostile_response_subclass() -> type:
    class _HostileResponse(RoughtimeV19ResponseSemantics):
        def __getattribute__(self, name: str) -> object:
            _HOSTILE_ACCESS.append(name)
            return object.__getattribute__(self, name)

    return _HostileResponse


@pytest.mark.parametrize("bad", [object(), None, b"", 0, "response"])
def test_wrong_response_type_rejected(bad) -> None:
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(bad, _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


@pytest.mark.parametrize("bad", [None, 0, "key", bytearray(_V01_PUBLIC_KEY), memoryview(_V01_PUBLIC_KEY)])
def test_wrong_key_type_rejected(bad) -> None:
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(), bad)
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_bytes_subclass_key_rejected() -> None:
    class _Bytes(bytes):
        pass

    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(), _Bytes(_V01_PUBLIC_KEY))
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_response_subclass_rejected_before_any_attribute_read() -> None:
    response = _response()
    hostile_cls = _define_hostile_response_subclass()
    hostile = hostile_cls(
        signature=response.signature,
        nonce=response.nonce,
        message_type=response.message_type,
        path=response.path,
        index=response.index,
        signed_response=response.signed_response,
        certificate=response.certificate,
        extensions=response.extensions,
        raw=response.raw,
    )
    _HOSTILE_ACCESS.clear()
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(hostile, _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE
    assert _HOSTILE_ACCESS == []


def test_hollow_exact_response_rejected() -> None:
    hollow = _hollow(RoughtimeV19ResponseSemantics)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(hollow, _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


@pytest.mark.parametrize("bad_raw", [b"", b"NOTROUGH", b"ROUGHTIM\x04\x00\x00\x00", bytearray(b"ROUGHTIM")])
def test_unparsable_response_raw_rejected(bad_raw) -> None:
    hollow = _hollow(RoughtimeV19ResponseSemantics, raw=bad_raw)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(hollow, _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_forged_nested_certificate_is_ignored_because_raw_is_reparsed() -> None:
    """A caller-forged nested CERT cannot influence the result: only the reparsed canonical artifact is used."""
    response = _response()
    forged = _hollow(
        RoughtimeV19ResponseSemantics,
        signature=response.signature,
        nonce=response.nonce,
        message_type=response.message_type,
        path=response.path,
        index=response.index,
        signed_response=response.signed_response,
        certificate=_hollow(
            RoughtimeV19CertificateSemantics,
            signature=bytes(64),
            delegation=_hollow(
                RoughtimeV19DelegationSemantics,
                pubk=bytes(32),
                min_time=0,
                max_time=0,
                extensions=(),
                raw=b"",
            ),
            extensions=(),
            raw=b"",
        ),
        extensions=response.extensions,
        raw=response.raw,
    )
    artifact = verify_roughtime_v19_certificate(forged, _V01_PUBLIC_KEY)
    assert artifact.certificate_signature == _V01_SIGNATURE
    assert artifact.delegation_raw == _V01_DELE_RAW


# ============================================================================================================
# Backend failure normalization (P2-1)
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
    """Any ordinary Exception from `.verify(...)` must surface as crypto_backend_failure, never raw."""
    import crypto_core.validation.roughtime_v19_certificate_verification as module

    class _Failing:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def verify(self, *args, **kwargs):
            raise failure("backend detail that must not leak")

    monkeypatch.setattr(module, "VerifyKey", _Failing)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.CRYPTO_BACKEND_FAILURE
    assert str(excinfo.value) == "crypto_backend_failure"
    assert "backend detail" not in str(excinfo.value)


@pytest.mark.parametrize("failure", _BACKEND_FAILURE_CLASSES, ids=lambda cls: cls.__name__)
def test_unexpected_backend_exception_from_construction_normalizes_to_backend_failure(failure, monkeypatch) -> None:
    """The broad catch must also cover VerifyKey CONSTRUCTION, not only .verify()."""
    import crypto_core.validation.roughtime_v19_certificate_verification as module

    def _failing_key(*args, **kwargs):
        raise failure("constructor detail that must not leak")

    monkeypatch.setattr(module, "VerifyKey", _failing_key)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.CRYPTO_BACKEND_FAILURE
    assert "constructor detail" not in str(excinfo.value)


def test_bad_signature_error_still_maps_to_cert_signature_invalid(monkeypatch) -> None:
    import crypto_core.validation.roughtime_v19_certificate_verification as module

    class _Failing:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def verify(self, *args, **kwargs):
            raise BadSignatureError("forged")

    monkeypatch.setattr(module, "VerifyKey", _Failing)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID


def test_nacl_valueerror_still_maps_to_cert_signature_invalid(monkeypatch) -> None:
    """Precedence matters: nacl's ValueError must be handled BEFORE the broad Exception catch."""
    import crypto_core.validation.roughtime_v19_certificate_verification as module

    assert NaclValueError is not ValueError

    class _Failing:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def verify(self, *args, **kwargs):
            raise NaclValueError("bad encoding")

    monkeypatch.setattr(module, "VerifyKey", _Failing)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY)
    assert excinfo.value.reason is R.CERT_SIGNATURE_INVALID


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_base_exception_from_backend_is_not_swallowed(interrupt, monkeypatch) -> None:
    """BaseException must propagate unchanged - the broad catch is `Exception`, never `BaseException`."""
    import crypto_core.validation.roughtime_v19_certificate_verification as module

    class _Failing:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def verify(self, *args, **kwargs):
            raise interrupt()

    monkeypatch.setattr(module, "VerifyKey", _Failing)
    with pytest.raises(interrupt):
        verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY)


def test_no_raw_backend_exception_leaks() -> None:
    for key in (_V17_PUBLIC_KEY, _V18_PUBLIC_KEY, bytes(31)):
        with pytest.raises(RoughtimeV19CertificateVerificationError):
            verify_roughtime_v19_certificate(_response(), key)
    for signature in (_V15_SIGNATURE, _V16_SIGNATURE):
        with pytest.raises(RoughtimeV19CertificateVerificationError):
            verify_roughtime_v19_certificate(_response(signature=signature), _V01_PUBLIC_KEY)


# ============================================================================================================
# Reason precedence
# ============================================================================================================
def test_wrong_input_type_precedes_everything() -> None:
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(object(), _V13_PUBLIC_KEY)
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_input_artifact_inconsistent_precedes_key_policy() -> None:
    hollow = _hollow(RoughtimeV19ResponseSemantics, raw=b"")
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(hollow, _V13_PUBLIC_KEY)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_key_policy_precedes_signature_policy() -> None:
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        verify_roughtime_v19_certificate(_response(signature=_V16_SIGNATURE), _V18_PUBLIC_KEY)
    assert excinfo.value.reason is R.LONG_TERM_PUBLIC_KEY_INVALID


# ============================================================================================================
# Output artifact contract
# ============================================================================================================
def test_artifact_declares_exactly_eight_public_fields_in_order() -> None:
    from crypto_core.validation.roughtime_v19_certificate_verification import _VERIFICATION_FIELD_NAMES

    assert _VERIFICATION_FIELD_NAMES == _EXPECTED_ARTIFACT_FIELDS
    assert len(_VERIFICATION_FIELD_NAMES) == 8
    for name in _EXPECTED_ARTIFACT_FIELDS:
        assert type(getattr(RoughtimeV19CertificateVerification, name)) is property


def _registered_state(artifact: RoughtimeV19CertificateVerification) -> tuple:
    """The eight verified values, obtained through the public validating reducer (never the registry)."""
    reducer, arguments = artifact.__reduce__()
    assert reducer.__name__ == "_rebuild_certificate_verification"
    state = arguments[0]
    assert type(state) is tuple
    return state


def test_storage_order_equals_declared_public_field_order() -> None:
    """Proves registered state index i IS public field i, so the layout cannot silently drift."""
    artifact = verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY)
    state = _registered_state(artifact)
    assert len(state) == 8
    for index, name in enumerate(_EXPECTED_ARTIFACT_FIELDS):
        assert state[index] == getattr(artifact, name), name


def test_artifact_field_names_avoid_forbidden_tokens() -> None:
    for name in _EXPECTED_ARTIFACT_FIELDS:
        for token in _FORBIDDEN_FIELD_TOKENS:
            assert token not in name


def test_state_validator_rejects_foreign_and_malformed_state() -> None:
    from crypto_core.validation.roughtime_v19_certificate_verification import (
        _ARTIFACT_INCONSISTENT,
        _validate_state_tuple,
    )

    genuine = _registered_state(verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY))
    for bad in (None, (), [*genuine], genuine[:7], (*genuine, b"extra"), _hollow(RoughtimeV19ResponseSemantics)):
        with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
            _validate_state_tuple(bad, _ARTIFACT_INCONSISTENT)
        assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT
    _validate_state_tuple(genuine, _ARTIFACT_INCONSISTENT)


def test_pickle_rebuild_helper_rejects_malformed_state() -> None:
    from crypto_core.validation.roughtime_v19_certificate_verification import _rebuild_certificate_verification

    state = _registered_state(verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY))
    malformed = (
        None,
        (),
        state[:7],
        (*state, b"extra"),
        list(state),
        (b"forged", *state[1:]),
        (state[0], _V09_PUBLIC_KEY, *state[2:]),
        (*state[:5], bytes(32), *state[6:]),
        (*state[:6], 0, state[7]),
        (*state[:7], 0),
        (bytearray(state[0]), *state[1:]),
    )
    for bad in malformed:
        with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
            _rebuild_certificate_verification(bad)
        assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT
    assert _rebuild_certificate_verification(state).delegation_raw == _V01_DELE_RAW


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("long_term_public_key", _V09_PUBLIC_KEY),
        ("certificate_signature", bytes(64)),
        ("delegation_raw", _V11_DELE_RAW),
        ("delegated_public_key", bytes(32)),
        ("min_time", 0),
        ("max_time", 0),
        ("certificate_raw", b""),
        ("response_raw", b""),
    ],
)
def test_altered_artifact_field_rejected(field, value) -> None:
    fields = _valid_artifact_fields()
    fields[field] = value
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        RoughtimeV19CertificateVerification(**fields)
    assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("response_raw", None),
        ("long_term_public_key", bytearray(_V01_PUBLIC_KEY)),
        ("min_time", "100"),
        ("max_time", True),
        ("delegation_raw", 0),
    ],
)
def test_wrong_artifact_field_type_rejected(field, value) -> None:
    fields = _valid_artifact_fields()
    fields[field] = value
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        RoughtimeV19CertificateVerification(**fields)
    assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT


# ============================================================================================================
# P1 regression: the proof is a sealed NON-CONTAINER with no instance storage
#
# Defect history. (1) @dataclass(frozen=True) only intercepts __setattr__ while keeping a writable instance
# __dict__, so `artifact.__dict__["delegated_public_key"] = forged` mutated a verified field after the fact.
# (2) Subclassing tuple removed the __dict__ but stored the values in the base object, and subclass overrides
# CANNOT intercept an explicit unbound base call - so tuple.__getitem__/__iter__/__repr__/__getnewargs__/
# __add__/count/index read that storage directly and returned forged proof state. The artifact now inherits
# straight from object and keeps no proof on the instance at all, so both surfaces are structurally absent.
# ============================================================================================================
def _artifact() -> RoughtimeV19CertificateVerification:
    return verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY)


def test_artifact_inherits_no_builtin_container_or_scalar_base() -> None:
    """The P1-1 architectural requirement: no built-in base whose unbound methods could read proof storage."""
    assert RoughtimeV19CertificateVerification.__mro__ == (RoughtimeV19CertificateVerification, object)
    assert RoughtimeV19CertificateVerification.__bases__ == (object,)
    for forbidden in (tuple, list, dict, set, frozenset, bytes, bytearray, str, int, float):
        assert not issubclass(RoughtimeV19CertificateVerification, forbidden), forbidden
    assert RoughtimeV19CertificateVerification.__name__ == "RoughtimeV19CertificateVerification"
    assert RoughtimeV19CertificateVerification.__qualname__ == "RoughtimeV19CertificateVerification"
    assert (
        RoughtimeV19CertificateVerification.__module__
        == "crypto_core.validation.roughtime_v19_certificate_verification"
    )


def test_artifact_has_no_instance_dict_and_only_a_weakref_slot() -> None:
    artifact = _artifact()
    assert RoughtimeV19CertificateVerification.__slots__ == ("__weakref__",)
    assert not hasattr(artifact, "__dict__")
    assert type(artifact).__dictoffset__ == 0
    assert "__dict__" not in dir(artifact)


def test_weakref_slot_cannot_be_repurposed_as_proof_storage() -> None:
    """The single slot exists only for registry lifecycle binding and is a read-only descriptor."""
    artifact = _artifact()
    for value in (b"forged", _V09_PUBLIC_KEY, ("forged",)):
        with pytest.raises(AttributeError):
            object.__setattr__(artifact, "__weakref__", value)
    with pytest.raises(AttributeError):
        object.__delattr__(artifact, "__weakref__")
    assert artifact.delegation_raw == _V01_DELE_RAW


def test_no_proof_field_is_a_writable_descriptor() -> None:
    for name in _EXPECTED_ARTIFACT_FIELDS:
        descriptor = getattr(RoughtimeV19CertificateVerification, name)
        assert type(descriptor) is property
        assert descriptor.fset is None, name
        assert descriptor.fdel is None, name


def test_vars_on_artifact_fails() -> None:
    with pytest.raises(TypeError):
        vars(_artifact())


def test_artifact_dunder_dict_access_and_replacement_fail() -> None:
    artifact = _artifact()
    with pytest.raises(AttributeError):
        _ = artifact.__dict__
    with pytest.raises(AttributeError):
        object.__setattr__(artifact, "__dict__", {"root_authentic": True})
    with pytest.raises(AttributeError):
        object.__delattr__(artifact, "__dict__")


@pytest.mark.parametrize("field", _EXPECTED_ARTIFACT_FIELDS)
def test_setattr_rejected_for_every_field(field) -> None:
    artifact = _artifact()
    with pytest.raises(AttributeError):
        setattr(artifact, field, _V09_PUBLIC_KEY)


@pytest.mark.parametrize("field", _EXPECTED_ARTIFACT_FIELDS)
def test_delattr_rejected_for_every_field(field) -> None:
    artifact = _artifact()
    with pytest.raises(AttributeError):
        delattr(artifact, field)


@pytest.mark.parametrize("field", _EXPECTED_ARTIFACT_FIELDS)
def test_object_setattr_cannot_replace_any_proof_field(field) -> None:
    """The exact reported defect: object.__setattr__/__delattr__ must not reach a verified field."""
    artifact = _artifact()
    before = getattr(artifact, field)
    with pytest.raises(AttributeError):
        object.__setattr__(artifact, field, _V09_PUBLIC_KEY)
    with pytest.raises(AttributeError):
        object.__delattr__(artifact, field)
    assert getattr(artifact, field) == before


@pytest.mark.parametrize("name", ["root_authentic", "signature_verified", "provider_id", "note"])
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
    for name in (*_EXPECTED_ARTIFACT_FIELDS, "root_authentic", "_cache", "__dict__"):
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
    """Exercise each distinct equality claim through operator calls to avoid redundant-comparison patterns."""
    first = _artifact()
    second = _artifact()
    assert operator.eq(first, second) is True
    assert operator.ne(first, second) is False
    plain = _registered_state(first)
    assert operator.eq(first, plain) is False
    assert operator.ne(first, plain) is True
    assert operator.eq(plain, first) is False
    assert operator.ne(plain, first) is True
    assert operator.ne(first, object()) is True
    with pytest.raises(AttributeError):
        object.__setattr__(second, "min_time", 0)
    assert operator.eq(second, first) is True


@pytest.mark.parametrize("impostor", ["tuple", "list", "dict", "set"])
def test_no_builtin_container_can_impersonate_a_proof(impostor) -> None:
    """A bare container carrying the same values is never equal to the proof in either direction."""
    artifact = _artifact()
    state = _registered_state(artifact)
    candidate = {
        "tuple": state,
        "list": list(state),
        "dict": dict(zip(_EXPECTED_ARTIFACT_FIELDS, state)),
        "set": set(state),
    }[impostor]
    assert operator.eq(artifact, candidate) is False
    assert operator.ne(artifact, candidate) is True
    assert operator.eq(candidate, artifact) is False
    assert operator.ne(candidate, artifact) is True


def test_inequality_and_hash_are_defined_explicitly_on_the_artifact() -> None:
    """Neither inequality nor hashing may fall back to a state-bearing built-in base implementation."""
    namespace = vars(RoughtimeV19CertificateVerification)
    assert "__eq__" in namespace
    assert "__ne__" in namespace
    assert "__hash__" in namespace
    assert RoughtimeV19CertificateVerification.__hash__ is not None


@pytest.mark.parametrize("operation", ["lt", "le", "gt", "ge"])
def test_ordering_is_inapplicable(operation) -> None:
    first = _artifact()
    second = _artifact()
    with pytest.raises(TypeError):
        getattr(operator, operation)(first, second)


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
    "__radd__",
    "__iadd__",
    "__mul__",
    "__rmul__",
    "__imul__",
    "__getnewargs__",
    "count",
    "index",
)


@pytest.mark.parametrize("name", _SEQUENCE_PROTOCOL_NAMES)
def test_sequence_protocol_is_absent_from_the_artifact(name) -> None:
    artifact = _artifact()
    assert not hasattr(RoughtimeV19CertificateVerification, name), name
    assert not hasattr(artifact, name), name


def test_sequence_operations_fail_without_exposing_proof_state() -> None:
    artifact = _artifact()
    operations = (
        ("len", lambda obj: len(obj)),
        ("iter", lambda obj: iter(obj)),
        ("for", lambda obj: [item for item in obj]),
        ("index", lambda obj: obj[0]),
        ("slice", lambda obj: obj[0:1]),
        ("membership", lambda obj: _V01_DELE_RAW in obj),
        ("unpack", lambda obj: [*obj]),
        ("reversed", lambda obj: reversed(obj)),
    )
    for label, operation in operations:
        with pytest.raises(TypeError) as excinfo:
            operation(artifact)
        rendered = str(excinfo.value)
        assert _V01_DELE_RAW.hex() not in rendered, label
        assert _V01_SIGNATURE.hex() not in rendered, label


def test_copy_deepcopy_and_pickle_stay_valid_and_immutable() -> None:
    artifact = _artifact()
    clones = (
        copy.copy(artifact),
        copy.deepcopy(artifact),
        pickle.loads(pickle.dumps(artifact)),  # noqa: S301 - round-trips this module's own artifact only
    )
    for clone in clones:
        assert type(clone) is RoughtimeV19CertificateVerification
        assert operator.eq(clone, artifact) is True
        assert hash(clone) == hash(artifact)
        assert not hasattr(clone, "__dict__")
        assert clone.delegation_raw == _V01_DELE_RAW
        assert clone.certificate_signature == _V01_SIGNATURE
        with pytest.raises(AttributeError):
            object.__setattr__(clone, "min_time", 0)


def test_pickle_payload_carries_no_registry_state() -> None:
    """Reconstruction uses the validating rebuild helper and never serializes registry internals."""
    artifact = _artifact()
    payload = pickle.dumps(artifact)
    assert b"_rebuild_certificate_verification" in payload
    assert b"registry" not in payload
    assert b"proven_state" not in payload
    restored = pickle.loads(payload)  # noqa: S301 - round-trips this module's own artifact only
    assert operator.eq(restored, artifact) is True


def test_verifier_artifact_fields_are_byte_identical_to_the_accepted_vectors() -> None:
    response = _response()
    artifact = verify_roughtime_v19_certificate(response, _V01_PUBLIC_KEY)
    assert artifact.response_raw == response.raw
    assert artifact.long_term_public_key == _V01_PUBLIC_KEY
    assert artifact.certificate_raw == response.certificate.raw
    assert artifact.certificate_signature == _V01_SIGNATURE
    assert artifact.delegation_raw == _V01_DELE_RAW
    assert artifact.delegated_public_key == _V01_DELE_RAW[32:64]
    assert artifact.min_time == _V01_MINT
    assert artifact.max_time == _V01_MAXT
    assert _registered_state(artifact) == (
        response.raw,
        _V01_PUBLIC_KEY,
        response.certificate.raw,
        _V01_SIGNATURE,
        _V01_DELE_RAW,
        _V01_DELE_RAW[32:64],
        _V01_MINT,
        _V01_MAXT,
    )


# ============================================================================================================
# P1 regression: explicit unbound built-in base calls are inapplicable and expose nothing
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
    ("tuple.__mul__", lambda obj: tuple.__mul__(obj, 2)),
    ("tuple.__eq__", lambda obj: tuple.__eq__(obj, ())),
    ("tuple.__ne__", lambda obj: tuple.__ne__(obj, ())),
    ("tuple.__lt__", lambda obj: tuple.__lt__(obj, ())),
    ("tuple.__hash__", lambda obj: tuple.__hash__(obj)),
    ("tuple.__len__", lambda obj: tuple.__len__(obj)),
)

_PROOF_TEXT_MARKERS = (
    _V01_DELE_RAW.hex(),
    _V01_SIGNATURE.hex(),
    _V01_PUBLIC_KEY.hex(),
    repr(_V01_DELE_RAW),
    repr(_V01_SIGNATURE),
    repr(_V01_PUBLIC_KEY),
)


def _assert_no_proof_state_in(value: object, label: str) -> None:
    rendered = repr(value)
    for marker in _PROOF_TEXT_MARKERS:
        assert marker not in rendered, label


@pytest.mark.parametrize("name,call", _TUPLE_BASE_CALLS, ids=lambda value: value if isinstance(value, str) else "")
@pytest.mark.parametrize("kind", ["genuine", "hollow"])
def test_unbound_tuple_base_calls_are_inapplicable_and_expose_nothing(name, call, kind) -> None:
    subject = _artifact() if kind == "genuine" else object.__new__(RoughtimeV19CertificateVerification)
    with pytest.raises(TypeError) as excinfo:
        call(subject)
    _assert_no_proof_state_in(str(excinfo.value), f"{kind}/{name}")


@pytest.mark.parametrize("base", [list, dict, bytes, bytearray, str, set, frozenset])
def test_other_builtin_base_calls_are_inapplicable_and_expose_nothing(base) -> None:
    artifact = _artifact()
    with pytest.raises(TypeError) as excinfo:
        base.__repr__(artifact)
    _assert_no_proof_state_in(str(excinfo.value), base.__name__)


def test_object_base_calls_expose_identity_but_no_proof_state() -> None:
    """object's own methods are reachable, but reveal identity only; public artifact methods still validate."""
    artifact = _artifact()
    hollow = object.__new__(RoughtimeV19CertificateVerification)
    for label, subject in (("genuine", artifact), ("hollow", hollow)):
        rendered = object.__repr__(subject)
        _assert_no_proof_state_in(rendered, f"object.__repr__/{label}")
        assert "RoughtimeV19CertificateVerification object at" in rendered
        assert type(object.__hash__(subject)) is int
    assert repr(artifact).startswith("RoughtimeV19CertificateVerification(response_raw=")
    assert hash(artifact) == hash(_artifact())
    with pytest.raises(RoughtimeV19CertificateVerificationError):
        repr(hollow)


def _artifact_method_node(name: str) -> ast.FunctionDef:
    matches = [
        child
        for node in ast.walk(_production_tree())
        if isinstance(node, ast.ClassDef) and node.name == "RoughtimeV19CertificateVerification"
        for child in node.body
        if isinstance(child, ast.FunctionDef) and child.name == name
    ]
    assert len(matches) == 1, name
    return matches[0]


@pytest.mark.parametrize("method_name", (*_EXPECTED_ARTIFACT_FIELDS, "__repr__", "__hash__", "__eq__", "__reduce__"))
def test_every_public_state_consumer_revalidates_through_proven_state(method_name) -> None:
    """Static causality pin: removing a public consumer's revalidation names that consumer as a failure."""
    method = _artifact_method_node(method_name)
    calls = {
        node.func.id for node in ast.walk(method) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "proven_state" in calls, method_name


def test_production_documents_exact_option_a_trust_boundary() -> None:
    """Pin the selected boundary without claiming secrets against excluded private-state compromise."""
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    assert source.count("SUPPORTED TRUST BOUNDARY (public/supported operations)") == 2
    assert source.count("EXCLUDED PRIVATE-STATE BOUNDARY") == 2
    for supported in (
        "hostile public inputs",
        "object.__setattr__",
        "object.__new__",
        "explicit unbound built-in base calls",
        "hash/equality/dict/set consumption",
        "pickle serialization and reconstruction",
        "stale-id or weakref lifecycle accidents",
    ):
        assert supported in source
    for excluded in (
        "private function ``__closure__`` cells",
        "mutation of private closure-cell contents",
        "monkeypatching private implementation functions or constants",
        "debugger/instrumentation compromise",
        "interpreter-memory modification",
        "native memory corruption",
        "arbitrary same-process code execution",
    ):
        assert excluded in source
    for false_claim in (
        "ordinary reflection",
        "caller can neither read through the object nor reach through the module namespace",
        "registry private to this class's factory closure",
        "closure-private",
    ):
        assert false_claim not in source


# ============================================================================================================
# White-box implementation invariants: registry identity, weakref ownership and lifecycle
#
# Direct closure inspection and every temporary registry mutation below are EXCLUDED private-state operations.
# They pin implementation behavior under unmodified state or synthetic lifecycle accidents; they do not claim
# that closure contents are secret or that deliberate private-registry rewriting is a supported attacker action.
# ============================================================================================================
def _closure_registry() -> dict:
    """White-box only: locate the closure-local registry; never a production API or secrecy assertion."""
    outer_cells = RoughtimeV19CertificateVerification.__hash__.__closure__ or ()
    proven_functions = []
    for cell in outer_cells:
        try:
            content = cell.cell_contents
        except ValueError:  # pragma: no cover - an empty implementation cell would fail below
            continue
        if callable(content) and getattr(content, "__name__", None) == "proven_state":
            proven_functions.append(content)
    assert len(proven_functions) == 1
    registries = []
    for cell in proven_functions[0].__closure__ or ():
        try:
            content = cell.cell_contents
        except ValueError:  # pragma: no cover - an empty implementation cell would fail below
            continue
        if type(content) is dict:
            registries.append(content)
    assert len(registries) == 1
    return registries[0]


def test_registry_is_closure_local_and_not_module_global() -> None:
    import crypto_core.validation.roughtime_v19_certificate_verification as module

    registry = _closure_registry()
    assert all(value is not registry for value in vars(module).values())
    assert all("registry" not in name.lower() for name in module.__all__)
    for hook_name in ("registry", "_registry", "get_registry", "_get_registry"):
        assert not hasattr(module, hook_name)


def test_registry_binds_one_exact_well_shaped_entry_per_live_artifact() -> None:
    registry = _closure_registry()
    baseline = len(registry)
    first = _artifact()
    second = _artifact()
    assert len(registry) == baseline + 2
    for artifact in (first, second):
        key = id(artifact)
        assert type(key) is int
        assert key in registry
        entry = registry[key]
        assert type(entry) is tuple
        assert len(entry) == 2
        reference, state = entry
        assert type(reference) is weakref.ReferenceType
        assert reference() is artifact
        assert reference.__callback__ is not None
        assert type(state) is tuple
        assert len(state) == 8
        assert tuple(type(value) for value in state) == (bytes, bytes, bytes, bytes, bytes, bytes, int, int)


def test_registry_entry_is_removed_when_the_artifact_dies() -> None:
    registry = _closure_registry()
    baseline = len(registry)
    artifact = _artifact()
    key = id(artifact)
    reference = weakref.ref(artifact)
    assert key in registry
    del artifact
    gc.collect()
    assert reference() is None
    assert key not in registry
    assert len(registry) == baseline


def test_failed_construction_leaves_no_registry_entry() -> None:
    registry = _closure_registry()
    baseline = len(registry)
    fields = _valid_artifact_fields()
    fields["min_time"] = 0
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        RoughtimeV19CertificateVerification(**fields)
    assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT
    assert len(registry) == baseline


def test_hollow_instance_has_no_registry_entry() -> None:
    registry = _closure_registry()
    baseline = len(registry)
    hollow = object.__new__(RoughtimeV19CertificateVerification)
    assert id(hollow) not in registry
    assert len(registry) == baseline


def test_whitebox_mismatched_weakref_never_authenticates_another_object() -> None:
    """Excluded registry mutation used only to pin the identity gate against a synthetic stale-id accident."""
    registry = _closure_registry()
    genuine = _artifact()
    state = _registered_state(genuine)
    impostor = object.__new__(RoughtimeV19CertificateVerification)
    key = id(impostor)
    assert key not in registry
    registry[key] = (weakref.ref(genuine), state)
    try:
        for consume in (lambda obj: obj.response_raw, repr, hash, lambda obj: obj.__reduce__()):
            with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
                consume(impostor)
            assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT
    finally:
        registry.pop(key, None)
    assert genuine.delegation_raw == _V01_DELE_RAW


def test_whitebox_dead_weakref_entry_never_authenticates() -> None:
    """Excluded registry mutation used only to pin fail-closed handling of a synthetic dead-reference entry."""
    registry = _closure_registry()
    template = _artifact()
    state = _registered_state(template)
    doomed = _artifact()
    reference = weakref.ref(doomed)
    del doomed
    gc.collect()
    assert reference() is None
    impostor = object.__new__(RoughtimeV19CertificateVerification)
    key = id(impostor)
    assert key not in registry
    registry[key] = (reference, state)
    try:
        with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
            _ = impostor.response_raw
        assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT
    finally:
        registry.pop(key, None)


def test_whitebox_stale_callback_deletes_only_the_entry_its_exact_weakref_owns() -> None:
    """A delayed old callback must not delete a newer entry under a reused integer identity key."""
    registry = _closure_registry()
    owner = _artifact()
    key = id(owner)
    owner_reference, owner_state = registry[key]
    replacement = _artifact()
    replacement_entry = registry[id(replacement)]
    callback = owner_reference.__callback__
    assert callback is not None
    registry[key] = replacement_entry
    try:
        callback(owner_reference)
        assert registry.get(key) is replacement_entry
    finally:
        registry[key] = (owner_reference, owner_state)
    assert owner.response_raw == _response().raw
    assert replacement.response_raw == _response().raw


def test_registry_lookup_uses_exact_int_identity_keys_without_artifact_hash_or_equality() -> None:
    artifact = _artifact()
    registry = _closure_registry()
    assert all(type(key) is int for key in registry)
    assert registry[id(artifact)][0]() is artifact
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    assert "entry = registry.get(id(artifact))" in source
    assert "registry[artifact]" not in source
    assert "registry.get(artifact)" not in source


# ============================================================================================================
# P1 regression: a hollow exact-type instance is consumable on no public artifact surface
# ============================================================================================================
_CONSUMPTION_SURFACES = (
    ("response_raw", lambda obj: obj.response_raw),
    ("long_term_public_key", lambda obj: obj.long_term_public_key),
    ("certificate_raw", lambda obj: obj.certificate_raw),
    ("certificate_signature", lambda obj: obj.certificate_signature),
    ("delegation_raw", lambda obj: obj.delegation_raw),
    ("delegated_public_key", lambda obj: obj.delegated_public_key),
    ("min_time", lambda obj: obj.min_time),
    ("max_time", lambda obj: obj.max_time),
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
    hollow = object.__new__(RoughtimeV19CertificateVerification)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        consume(hollow)
    assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT, surface


def test_hollow_instance_never_equals_or_collides_with_a_genuine_proof() -> None:
    genuine = _artifact()
    hollow = object.__new__(RoughtimeV19CertificateVerification)
    mapping = {genuine: "proof"}
    operations = (
        lambda: operator.eq(genuine, hollow),
        lambda: operator.eq(hollow, genuine),
        lambda: operator.ne(genuine, hollow),
        lambda: operator.ne(hollow, genuine),
        lambda: hollow in {genuine},
        lambda: mapping[hollow],
    )
    for consume in operations:
        with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
            consume()
        assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT


# ============================================================================================================
# Artifact sealing
# ============================================================================================================
_SEAL_LEDGER: list[str] = []


def _define_ordinary_subclass() -> type:
    class _Ordinary(RoughtimeV19CertificateVerification):
        pass

    return _Ordinary


def _define_new_override_subclass() -> type:
    class _NoValidation(RoughtimeV19CertificateVerification):
        def __new__(cls, **fields: object) -> object:
            _SEAL_LEDGER.append("__new__")
            return object.__new__(cls)

    return _NoValidation


def _define_getattribute_subclass() -> type:
    class _Hostile(RoughtimeV19CertificateVerification):
        def __getattribute__(self, name: str) -> object:
            _SEAL_LEDGER.append("__getattribute__")
            return object.__getattribute__(self, name)

    return _Hostile


def _define_equality_override_subclass() -> type:
    class _AlwaysEqual(RoughtimeV19CertificateVerification):
        def __eq__(self, other: object) -> bool:
            _SEAL_LEDGER.append("__eq__")
            return True

        def __hash__(self) -> int:
            _SEAL_LEDGER.append("__hash__")
            return 0

    return _AlwaysEqual


def test_every_subclass_form_is_sealed() -> None:
    _SEAL_LEDGER.clear()
    for definer in (
        _define_ordinary_subclass,
        _define_new_override_subclass,
        _define_getattribute_subclass,
        _define_equality_override_subclass,
    ):
        with pytest.raises(TypeError) as excinfo:
            definer()
        assert type(excinfo.value) is TypeError
        assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE
    with pytest.raises(TypeError) as excinfo:
        type("_Dynamic", (RoughtimeV19CertificateVerification,), {})
    assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE
    assert _SEAL_LEDGER == []


# ============================================================================================================
# Error and profile contract
# ============================================================================================================
def test_profile_id_is_exact() -> None:
    assert ROUGHTIME_V19_CERTIFICATE_VERIFICATION_PROFILE_ID == _EXPECTED_PROFILE_ID


def test_reason_enum_is_exactly_six_members_in_order() -> None:
    assert tuple(member.value for member in R) == _EXPECTED_REASON_VALUES
    assert len(R) == 6


def test_error_str_is_reason_value_and_reason_is_exact() -> None:
    for member in R:
        error = RoughtimeV19CertificateVerificationError(member)
        assert str(error) == member.value
        assert error.reason is member


@pytest.mark.parametrize("bad", ["cert_signature_invalid", 0, None, object()])
def test_error_rejects_non_member_reason(bad) -> None:
    with pytest.raises(TypeError) as excinfo:
        RoughtimeV19CertificateVerificationError(bad)
    assert str(excinfo.value) == _EXPECTED_REASON_TYPE_MESSAGE


def test_error_rejects_hostile_value_property_before_reading_it() -> None:
    reads: list[str] = []

    class _HostileReason:
        @property
        def value(self) -> str:
            reads.append("value")
            return "cert_signature_invalid"

    with pytest.raises(TypeError):
        RoughtimeV19CertificateVerificationError(_HostileReason())
    assert reads == []


@pytest.mark.parametrize("locked", ["reason", "_reason", "args"])
def test_error_locked_attributes_are_immutable(locked) -> None:
    error = RoughtimeV19CertificateVerificationError(R.WRONG_INPUT_TYPE)
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
        "ROUGHTIME_V19_CERTIFICATE_VERIFICATION_PROFILE_ID",
        "RoughtimeV19CertificateVerification",
        "RoughtimeV19CertificateVerificationError",
        "RoughtimeV19CertificateVerificationReason",
        "verify_roughtime_v19_certificate",
    ]


def _enclosing_function_names(tree: ast.Module) -> dict[ast.ExceptHandler, str]:
    """Map each except handler to the name of its INNERMOST enclosing function."""
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
    """No BaseException-family catch anywhere, and the ONE broad `except Exception` is pinned to the backend.

    A broad catch is authorized only around the third-party backend construction/verification calls, because
    native code may raise classes no enumerated list predicts and a cryptographic boundary must normalize them
    rather than leak. Anywhere else it could swallow a real defect, so its location is asserted exactly.
    """
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
    assert broad_catch_functions == ["_verify_detached"]


def test_production_uses_no_isinstance() -> None:
    calls = {
        node.func.id
        for node in ast.walk(_production_tree())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "isinstance" not in calls


def test_production_performs_no_srep_or_inclusion_or_provider_work() -> None:
    """Executable surface only: docstrings may NAME these as non-claims, but no code may touch them."""
    tree = _production_tree()
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    identifiers = {token.lower() for token in attributes | names}
    for forbidden in (
        "root",
        "server_key_id",
        "srv",
        "connector_ready_dialects",
        "mt4_verifier_profile_selected",
        "sha512",
        "verify_roughtime_v19_request_inclusion",
    ):
        assert forbidden not in identifiers
    assert "signed_response" not in identifiers


def test_production_reads_no_clock_or_randomness() -> None:
    modules: set[str] = set()
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
    for forbidden in ("time", "datetime", "random", "secrets", "os", "socket", "requests", "pathlib"):
        assert forbidden not in modules
