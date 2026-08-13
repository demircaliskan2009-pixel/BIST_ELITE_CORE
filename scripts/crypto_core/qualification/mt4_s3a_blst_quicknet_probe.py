"""MT4-S3A qualification-only ctypes probe over the narrow blst v0.3.17 C ABI.

SCOPE.  This module is qualification infrastructure, never a product verifier.  It admits no
dependency, selects no verifier profile, and promotes no readiness or connector state.  No
crypto_core product module imports it.

DETERMINISM.  Loading the native library reads the filesystem ONCE during construction; that is
reported as ``NATIVE_LIBRARY_FILESYSTEM_LOAD_AT_INIT`` and must never be restated as a per-call
filesystem dependency.  A verification call itself performs no filesystem, network, clock,
environment or randomness access.

The module deliberately imports no network capability at all, so "no network at verification time"
is a structural property of the file rather than a runtime promise.
"""

from __future__ import annotations

import ctypes
import hashlib

NATIVE_LIBRARY_FILESYSTEM_LOAD_AT_INIT = True
FILESYSTEM_REQUIRED_PER_VERIFY_CALL = False

ENTRY_POINT = "mt4_s3a_verify_quicknet_bls"
# Qualification scaffolding only; carries no verification decision.
GENERATOR_ENTRY_POINT = "mt4_s3a_qualification_g2_generator_compressed"

PUBLIC_KEY_LEN = 96
SIGNATURE_LEN = 48
MESSAGE_DIGEST_LEN = 32

QUICKNET_DST = b"BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_"
QUICKNET_SCHEME = "bls-unchained-g1-rfc9380"

# Bounded status taxonomy pinned to the C ABI.  Upstream BLST_ERROR integers never appear here.
STATUS_OK = 0
STATUS_NULL_INPUT = 1
STATUS_BAD_LENGTH = 2
STATUS_PK_BAD_ENCODING = 3
STATUS_PK_NON_CANONICAL = 4
STATUS_PK_INFINITY = 5
STATUS_PK_NOT_IN_GROUP = 6
STATUS_SIG_BAD_ENCODING = 7
STATUS_SIG_NON_CANONICAL = 8
STATUS_SIG_INFINITY = 9
STATUS_SIG_NOT_IN_GROUP = 10
STATUS_VERIFY_FAILED = 11

STATUS_NAMES = {
    STATUS_OK: "OK",
    STATUS_NULL_INPUT: "NULL_INPUT",
    STATUS_BAD_LENGTH: "BAD_LENGTH",
    STATUS_PK_BAD_ENCODING: "PK_BAD_ENCODING",
    STATUS_PK_NON_CANONICAL: "PK_NON_CANONICAL",
    STATUS_PK_INFINITY: "PK_INFINITY",
    STATUS_PK_NOT_IN_GROUP: "PK_NOT_IN_GROUP",
    STATUS_SIG_BAD_ENCODING: "SIG_BAD_ENCODING",
    STATUS_SIG_NON_CANONICAL: "SIG_NON_CANONICAL",
    STATUS_SIG_INFINITY: "SIG_INFINITY",
    STATUS_SIG_NOT_IN_GROUP: "SIG_NOT_IN_GROUP",
    STATUS_VERIFY_FAILED: "VERIFY_FAILED",
}


class QualificationProbeError(RuntimeError):
    """Raised for probe-boundary faults; never used to report a verification verdict."""


def quicknet_message_digest(round_number: int) -> bytes:
    """Return SHA256(uint64_big_endian(round)) -- the exact Quicknet signed message."""
    if type(round_number) is not int or isinstance(round_number, bool):
        raise QualificationProbeError("round must be an exact int")
    if round_number < 0 or round_number > 0xFFFFFFFFFFFFFFFF:
        raise QualificationProbeError("round out of uint64 range")
    return hashlib.sha256(round_number.to_bytes(8, "big")).digest()


def _exact_bytes(value: object, name: str) -> bytes:
    """Reject non-bytes and mutable aliases; return an immutable snapshot."""
    if type(value) is bytes:
        return value
    if type(value) is bytearray or type(value) is memoryview:
        # Copy once so a later caller mutation cannot reach the native call.
        return bytes(value)
    raise QualificationProbeError(name + " must be bytes")


class QuicknetQualificationProbe:
    """Thin ctypes binding to the qualification shim.

    A native load failure raises ``QualificationProbeError`` and is never collapsed into a
    verification success or a verification failure.
    """

    def __init__(self, library_path: str) -> None:
        try:
            library = ctypes.CDLL(str(library_path))
        except OSError as error:
            raise QualificationProbeError("native qualification library failed to load") from error
        try:
            entry = getattr(library, ENTRY_POINT)
        except AttributeError as error:
            raise QualificationProbeError("native qualification entry point is missing") from error
        entry.argtypes = (
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.c_char_p,
            ctypes.c_size_t,
        )
        entry.restype = ctypes.c_int
        try:
            generator = getattr(library, GENERATOR_ENTRY_POINT)
        except AttributeError as error:
            raise QualificationProbeError("qualification scaffolding entry point is missing") from error
        generator.argtypes = (ctypes.c_char_p, ctypes.c_size_t)
        generator.restype = ctypes.c_int
        self._library = library
        self._entry = entry
        self._generator = generator

    def g2_generator_compressed(self) -> bytes:
        """Return the compressed G2 generator; qualification scaffolding, never a trust decision."""
        buffer = ctypes.create_string_buffer(PUBLIC_KEY_LEN)
        status = self._generator(buffer, PUBLIC_KEY_LEN)
        if status != STATUS_OK:
            raise QualificationProbeError("scaffolding generator failed with status " + str(status))
        return bytes(buffer.raw[:PUBLIC_KEY_LEN])

    def verify(self, public_key: object, signature: object, message_digest: object) -> int:
        """Return one bounded MT4_S3A status code."""
        key_bytes = _exact_bytes(public_key, "public_key")
        signature_bytes = _exact_bytes(signature, "signature")
        digest_bytes = _exact_bytes(message_digest, "message_digest")
        # The native side re-checks every bound; these gates keep an obviously wrong call from
        # reaching the ABI at all.
        if len(key_bytes) != PUBLIC_KEY_LEN:
            return STATUS_BAD_LENGTH
        if len(signature_bytes) != SIGNATURE_LEN:
            return STATUS_BAD_LENGTH
        if len(digest_bytes) != MESSAGE_DIGEST_LEN:
            return STATUS_BAD_LENGTH
        status = self._entry(
            key_bytes,
            len(key_bytes),
            signature_bytes,
            len(signature_bytes),
            digest_bytes,
            len(digest_bytes),
        )
        if status not in STATUS_NAMES:
            raise QualificationProbeError("native shim returned an out-of-inventory status")
        return status

    def verify_unbounded(self, public_key: object, signature: object, message_digest: object) -> int:
        """Bypass the Python length pre-gates so the NATIVE length gates can be proven directly."""
        key_bytes = _exact_bytes(public_key, "public_key")
        signature_bytes = _exact_bytes(signature, "signature")
        digest_bytes = _exact_bytes(message_digest, "message_digest")
        status = self._entry(
            key_bytes,
            len(key_bytes),
            signature_bytes,
            len(signature_bytes),
            digest_bytes,
            len(digest_bytes),
        )
        if status not in STATUS_NAMES:
            raise QualificationProbeError("native shim returned an out-of-inventory status")
        return status


def status_name(status: int) -> str:
    if status not in STATUS_NAMES:
        raise QualificationProbeError("unknown status")
    return STATUS_NAMES[status]
