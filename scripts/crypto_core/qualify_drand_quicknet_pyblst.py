"""MT4-S3A Drand Quicknet dependency qualification logic (QUALIFICATION ONLY, NOT PRODUCTION).

This module is a qualification harness for a CANDIDATE dependency profile. It is deliberately NOT part
of any product runtime path, is never imported by product code, and admits nothing:

* it does not admit a dependency profile;
* it does not admit a fixture corpus;
* it does not select an MT-4 verifier profile;
* it does not approve a provider operationally;
* it does not prove machine time, a timestamp origin, proof verification or quorum countability;
* it does not promote readiness or connectors.

It performs NO acquisition and NO network, clock, filesystem-discovery or environment access. Every
input is supplied explicitly by the caller. ``pyblst`` is imported lazily and only inside the
verification entry point, so importing this module never requires the candidate dependency.

Qualification finding pinned by this module (see the qualification document): pyblst 0.3.15 declares
``hash_to_group(arg1, arg2)`` with internal variable names ``dst``/``msg``, but forwards them to
``blst_hash_to_g1(out, msg, msg_len, DST, DST_len, aug, aug_len)`` in that positional order. The TRUE
call order is therefore ``(message, dst)``. Calling it in the documented-name order silently produces a
different, self-consistent curve point that never verifies.
"""

from __future__ import annotations

import hashlib
from enum import Enum

__all__ = (
    "DRAND_QUICKNET_QUALIFICATION_PROFILE_ID",
    "QuicknetQualificationReason",
    "quicknet_message_digest",
    "quicknet_randomness",
    "quicknet_round_time",
    "qualify_quicknet_round",
)

DRAND_QUICKNET_QUALIFICATION_PROFILE_ID = "MT4-S3A-DRAND-QUICKNET-QUALIFICATION-CANDIDATE.v1"

# Candidate dependency profile. CANDIDATE ONLY - NOT ADMITTED.
CANDIDATE_DEPENDENCY_PROFILE_ID = "D-DEP-DRAND-PYBLST-0.3.15-CANDIDATE.v1"
CANDIDATE_PACKAGE_NAME = "pyblst"
CANDIDATE_PACKAGE_VERSION = "0.3.15"

# Quicknet chain identity, reverified from official primary sources during qualification.
QUICKNET_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
QUICKNET_BEACON_ID = "quicknet"
QUICKNET_SCHEME_ID = "bls-unchained-g1-rfc9380"
QUICKNET_PERIOD_SECONDS = 3
QUICKNET_GENESIS_TIME_SECONDS = 1_692_803_367
QUICKNET_DST = b"BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_"

# BLS12-381 G2 generator, compressed. Obtained from the OFFICIAL drand v2.1.6 KeyGroup base point.
BLS12_381_G2_GENERATOR_COMPRESSED = bytes.fromhex(
    "93e02b6052719f607dacd3a088274f65596bd0d09920b61ab5da61bbdc7f5049"
    "334cf11213945d57e5ac7d055d042b7e024aa2b2f08f0a91260805272dc51051"
    "c6e47ad4fa403b02b4510b647ae3d1770bac0326a805bbefd48056c8c121bdb8"
)

_PUBLIC_KEY_LENGTH = 96
_SIGNATURE_LENGTH = 48
_RANDOMNESS_LENGTH = 32
_ROUND_BYTE_LENGTH = 8
_MAX_ROUND = (1 << 64) - 1
_MAX_HASH_TO_CURVE_MESSAGE = 255
_HEX_CHARS = frozenset("0123456789abcdef")


class QuicknetQualificationReason(str, Enum):
    """Closed qualification failure inventory. No caller bytes or repr ever enter a diagnostic."""

    WRONG_INPUT_TYPE = "wrong_input_type"
    FIELD_INVENTORY_INVALID = "field_inventory_invalid"
    FIELD_TYPE_INVALID = "field_type_invalid"
    RESOURCE_BOUND_EXCEEDED = "resource_bound_exceeded"
    CHAIN_PROFILE_BINDING_INVALID = "chain_profile_binding_invalid"
    ROUND_INVALID = "round_invalid"
    PUBLIC_KEY_ENCODING_INVALID = "public_key_encoding_invalid"
    SIGNATURE_ENCODING_INVALID = "signature_encoding_invalid"
    PUBLIC_KEY_POINT_INVALID = "public_key_point_invalid"
    SIGNATURE_POINT_INVALID = "signature_point_invalid"
    POINT_AT_INFINITY_REJECTED = "point_at_infinity_rejected"
    SUBGROUP_CHECK_FAILED = "subgroup_check_failed"
    NON_CANONICAL_ENCODING = "non_canonical_encoding"
    MESSAGE_ENCODING_INVALID = "message_encoding_invalid"
    DST_MISMATCH = "dst_mismatch"
    SIGNATURE_VERIFICATION_FAILED = "signature_verification_failed"
    RANDOMNESS_MISMATCH = "randomness_mismatch"
    DEPENDENCY_PROFILE_UNAVAILABLE = "dependency_profile_unavailable"
    DEPENDENCY_VERSION_MISMATCH = "dependency_version_mismatch"
    DEPENDENCY_ARTIFACT_HASH_MISMATCH = "dependency_artifact_hash_mismatch"
    DEPENDENCY_EXCEPTION = "dependency_exception"
    REFERENCE_VERIFIER_MISMATCH = "reference_verifier_mismatch"
    FIXTURE_PROVENANCE_INVALID = "fixture_provenance_invalid"
    FIXTURE_LICENSE_UNRESOLVED = "fixture_license_unresolved"
    GOVERNANCE_STRUCTURAL_VIOLATION = "governance_structural_violation"
    ARTIFACT_INCONSISTENT = "artifact_inconsistent"
    QUALIFIED = "qualified"


def quicknet_message_digest(round_number: int) -> bytes:
    """Exact Quicknet signed message: sha256(round as 8-byte unsigned big-endian)."""
    if type(round_number) is not int or type(round_number) is bool:
        raise TypeError("round_number must be an exact int")
    if round_number < 1 or round_number > _MAX_ROUND:
        raise ValueError("round_number out of range")
    return hashlib.sha256(round_number.to_bytes(_ROUND_BYTE_LENGTH, "big", signed=False)).digest()


def quicknet_randomness(signature_bytes: bytes) -> bytes:
    """Exact Quicknet randomness: sha256 over the original exact 48 signature bytes."""
    if type(signature_bytes) is not bytes:
        raise TypeError("signature_bytes must be exact bytes")
    if len(signature_bytes) != _SIGNATURE_LENGTH:
        raise ValueError("signature_bytes must be exactly 48 bytes")
    return hashlib.sha256(signature_bytes).digest()


def quicknet_round_time(round_number: int, genesis_time: int, period: int) -> int:
    """Deterministic publication time: genesis + (round - 1) * period. Reads no ambient clock."""
    for value in (round_number, genesis_time, period):
        if type(value) is not int or type(value) is bool:
            raise TypeError("round_number, genesis_time and period must be exact ints")
    if round_number < 1 or round_number > _MAX_ROUND:
        raise ValueError("round_number out of range")
    return genesis_time + (round_number - 1) * period


def _is_canonical_infinity(raw: bytes) -> bool:
    """Canonical compressed point at infinity: compression+infinity bits set, all other bits zero."""
    if not raw:
        return False
    return raw[0] & 0x40 == 0x40 and raw[0] & 0x3F == 0 and all(byte == 0 for byte in raw[1:])


def _load_candidate_dependency():
    """Lazily import the candidate dependency. Returns (module, reason). Fails closed when absent."""
    try:
        import pyblst
    except ImportError:
        return None, QuicknetQualificationReason.DEPENDENCY_PROFILE_UNAVAILABLE
    try:
        import importlib.metadata as importlib_metadata

        observed = importlib_metadata.version(CANDIDATE_PACKAGE_NAME)
    except importlib_metadata.PackageNotFoundError:
        return None, QuicknetQualificationReason.DEPENDENCY_PROFILE_UNAVAILABLE
    if observed != CANDIDATE_PACKAGE_VERSION:
        return None, QuicknetQualificationReason.DEPENDENCY_VERSION_MISMATCH
    return pyblst, None


def qualify_quicknet_round(
    *,
    round_number: int,
    public_key_bytes: bytes,
    signature_bytes: bytes,
    chain_hash: str,
    dst: bytes = QUICKNET_DST,
    expected_randomness: bytes | None = None,
    genesis_time: int = QUICKNET_GENESIS_TIME_SECONDS,
    period: int = QUICKNET_PERIOD_SECONDS,
) -> tuple[bool, QuicknetQualificationReason, dict[str, object]]:
    """Deterministically qualify one Quicknet round. Returns (qualified, closed_reason, details).

    Admits nothing. A ``True`` result means only that the supplied bytes satisfy the structural and
    cryptographic checks of the candidate profile under the candidate dependency.
    """
    reason_type = QuicknetQualificationReason

    if type(round_number) is not int or type(round_number) is bool:
        return False, reason_type.WRONG_INPUT_TYPE, {}
    if type(public_key_bytes) is not bytes or type(signature_bytes) is not bytes:
        return False, reason_type.WRONG_INPUT_TYPE, {}
    if type(dst) is not bytes or type(chain_hash) is not str:
        return False, reason_type.WRONG_INPUT_TYPE, {}
    for value in (genesis_time, period):
        if type(value) is not int or type(value) is bool:
            return False, reason_type.FIELD_TYPE_INVALID, {}

    if round_number < 1 or round_number > _MAX_ROUND:
        return False, reason_type.ROUND_INVALID, {}
    if len(chain_hash) != 64 or not all(char in _HEX_CHARS for char in chain_hash):
        return False, reason_type.CHAIN_PROFILE_BINDING_INVALID, {}
    if chain_hash != QUICKNET_CHAIN_HASH:
        return False, reason_type.CHAIN_PROFILE_BINDING_INVALID, {}
    if len(public_key_bytes) != _PUBLIC_KEY_LENGTH:
        return False, reason_type.PUBLIC_KEY_ENCODING_INVALID, {}
    if len(signature_bytes) != _SIGNATURE_LENGTH:
        return False, reason_type.SIGNATURE_ENCODING_INVALID, {}
    if dst != QUICKNET_DST:
        return False, reason_type.DST_MISMATCH, {}

    message = quicknet_message_digest(round_number)
    if len(message) > _MAX_HASH_TO_CURVE_MESSAGE:
        return False, reason_type.MESSAGE_ENCODING_INVALID, {}

    # Reject canonical infinity encodings BEFORE any pairing work.
    if _is_canonical_infinity(signature_bytes) or _is_canonical_infinity(public_key_bytes):
        return False, reason_type.POINT_AT_INFINITY_REJECTED, {}

    pyblst, dependency_reason = _load_candidate_dependency()
    if dependency_reason is not None:
        return False, dependency_reason, {}

    try:
        public_key_point = pyblst.BlstP2Element.uncompress(public_key_bytes)
    except ValueError as error:
        if "NOT_IN_GROUP" in str(error):
            return False, reason_type.SUBGROUP_CHECK_FAILED, {}
        return False, reason_type.PUBLIC_KEY_POINT_INVALID, {}
    except Exception:
        return False, reason_type.DEPENDENCY_EXCEPTION, {}

    try:
        signature_point = pyblst.BlstP1Element.uncompress(signature_bytes)
    except ValueError as error:
        if "NOT_IN_GROUP" in str(error):
            return False, reason_type.SUBGROUP_CHECK_FAILED, {}
        return False, reason_type.SIGNATURE_POINT_INVALID, {}
    except Exception:
        return False, reason_type.DEPENDENCY_EXCEPTION, {}

    if bytes(public_key_point.compress()) != public_key_bytes:
        return False, reason_type.NON_CANONICAL_ENCODING, {}
    if bytes(signature_point.compress()) != signature_bytes:
        return False, reason_type.NON_CANONICAL_ENCODING, {}

    try:
        # TRUE pyblst order is (message, dst) despite the upstream variable naming.
        message_point = pyblst.BlstP1Element.hash_to_group(message, dst)
        generator_point = pyblst.BlstP2Element.uncompress(BLS12_381_G2_GENERATOR_COMPRESSED)
        left = pyblst.miller_loop(signature_point, generator_point)
        right = pyblst.miller_loop(message_point, public_key_point)
        verified = pyblst.final_verify(left, right)
    except Exception:
        return False, reason_type.DEPENDENCY_EXCEPTION, {}

    if verified is not True:
        return False, reason_type.SIGNATURE_VERIFICATION_FAILED, {}

    randomness = quicknet_randomness(signature_bytes)
    if expected_randomness is not None:
        if type(expected_randomness) is not bytes:
            return False, reason_type.FIELD_TYPE_INVALID, {}
        if len(expected_randomness) != _RANDOMNESS_LENGTH:
            return False, reason_type.FIELD_TYPE_INVALID, {}
        if randomness != expected_randomness:
            return False, reason_type.RANDOMNESS_MISMATCH, {}

    return (
        True,
        reason_type.QUALIFIED,
        {
            "message_digest_hex": message.hex(),
            "randomness_hex": randomness.hex(),
            "round_time": quicknet_round_time(round_number, genesis_time, period),
            "dependency_admitted": False,
            "fixture_corpus_admitted": False,
            "provider_operationally_approved": False,
            "readiness_promoted": False,
        },
    )
