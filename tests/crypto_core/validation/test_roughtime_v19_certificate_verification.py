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
import importlib.metadata
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

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
        "dataclasses",
        "enum",
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
    from nacl.exceptions import BadSignatureError
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


def test_small_order_inventory_is_exactly_seven_and_matches_production() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    assert len(_SMALL_ORDER_ENCODINGS) == _SMALL_ORDER_COUNT
    assert len(set(_SMALL_ORDER_ENCODINGS)) == _SMALL_ORDER_COUNT
    for encoding in _SMALL_ORDER_ENCODINGS:
        assert encoding.hex() in source
    assert "ed25519_ref10.c" in source
    assert "1.6.2" in source


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
def test_artifact_has_exactly_eight_fields_in_order() -> None:
    assert tuple(RoughtimeV19CertificateVerification.__dataclass_fields__) == _EXPECTED_ARTIFACT_FIELDS
    assert len(RoughtimeV19CertificateVerification.__dataclass_fields__) == 8


def test_artifact_field_names_avoid_forbidden_tokens() -> None:
    for name in RoughtimeV19CertificateVerification.__dataclass_fields__:
        for token in _FORBIDDEN_FIELD_TOKENS:
            assert token not in name


def test_verifier_artifact_namespace_is_exactly_eight_keys() -> None:
    artifact = verify_roughtime_v19_certificate(_response(), _V01_PUBLIC_KEY)
    assert type(artifact.__dict__) is dict
    assert sorted(artifact.__dict__) == sorted(_EXPECTED_ARTIFACT_FIELDS)


def _tainted(**extra: object) -> RoughtimeV19CertificateVerification:
    artifact = RoughtimeV19CertificateVerification(**_valid_artifact_fields())
    for name, value in extra.items():
        object.__setattr__(artifact, name, value)
    return artifact


@pytest.mark.parametrize(
    "extra",
    [
        {"root_authentic": True},
        {"signature_verified": True},
        {"provider_id": "cloudflare"},
        {"_cache": {"trusted": True}},
        {"note": "innocuous"},
    ],
)
def test_extra_artifact_state_rejected(extra) -> None:
    tainted = _tainted(**extra)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        RoughtimeV19CertificateVerification.__post_init__(tainted)
    assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT


def test_non_str_namespace_key_rejected() -> None:
    artifact = RoughtimeV19CertificateVerification(**_valid_artifact_fields())
    artifact.__dict__[42] = "foreign"
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        RoughtimeV19CertificateVerification.__post_init__(artifact)
    assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT


def test_dict_subclass_namespace_rejected() -> None:
    class _Dict(dict):
        def __len__(self) -> int:
            return 8

    artifact = RoughtimeV19CertificateVerification(**_valid_artifact_fields())
    substituted = _Dict(artifact.__dict__)
    substituted["root_authentic"] = True
    object.__setattr__(artifact, "__dict__", substituted)
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        RoughtimeV19CertificateVerification.__post_init__(artifact)
    assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT


def test_missing_and_renamed_output_field_rejected() -> None:
    artifact = RoughtimeV19CertificateVerification(**_valid_artifact_fields())
    del artifact.__dict__["min_time"]
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        RoughtimeV19CertificateVerification.__post_init__(artifact)
    assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT
    renamed = RoughtimeV19CertificateVerification(**_valid_artifact_fields())
    value = renamed.__dict__.pop("max_time")
    renamed.__dict__["maxtime"] = value
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        RoughtimeV19CertificateVerification.__post_init__(renamed)
    assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT


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


def test_unbound_post_init_with_foreign_object_rejected() -> None:
    foreign = _hollow(RoughtimeV19ResponseSemantics, raw=b"")
    with pytest.raises(RoughtimeV19CertificateVerificationError) as excinfo:
        RoughtimeV19CertificateVerification.__post_init__(foreign)
    assert excinfo.value.reason is R.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT


def test_artifact_is_frozen() -> None:
    artifact = RoughtimeV19CertificateVerification(**_valid_artifact_fields())
    with pytest.raises(FrozenInstanceError):
        artifact.min_time = 5


# ============================================================================================================
# Artifact sealing
# ============================================================================================================
_SEAL_LEDGER: list[str] = []


def _define_ordinary_subclass() -> type:
    class _Ordinary(RoughtimeV19CertificateVerification):
        pass

    return _Ordinary


def _define_post_init_subclass() -> type:
    class _NoValidation(RoughtimeV19CertificateVerification):
        def __post_init__(self) -> None:
            _SEAL_LEDGER.append("__post_init__")

    return _NoValidation


def _define_getattribute_subclass() -> type:
    class _Hostile(RoughtimeV19CertificateVerification):
        def __getattribute__(self, name: str) -> object:
            _SEAL_LEDGER.append("__getattribute__")
            return object.__getattribute__(self, name)

    return _Hostile


def test_every_subclass_form_is_sealed() -> None:
    _SEAL_LEDGER.clear()
    for definer in (_define_ordinary_subclass, _define_post_init_subclass, _define_getattribute_subclass):
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


def test_production_never_catches_base_exception() -> None:
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            names = [child.id for child in ast.walk(node.type) if isinstance(child, ast.Name)]
            for forbidden in ("BaseException", "KeyboardInterrupt", "SystemExit", "GeneratorExit", "Exception"):
                assert forbidden not in names


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
