"""Offline qualification binding; does not admit a TSA, root or native binary."""

from __future__ import annotations

import ctypes as c
from dataclasses import dataclass, field

from scripts.crypto_core.qualification.c_native_formats import QualificationError
from scripts.crypto_core.qualification.c_native_loader import CandidateLibrary

REQUIRED_FLAGS = 0x6F
OPENSSL_VERSION = 0x30500090
EXPORTS = (
    "cqual_abi_version",
    "cqual_openssl_version",
    "cqual_required_ts_flags",
    "cqual_verify_rfc3161",
    "cqual_cleanup",
)
STATUSES = (
    "VERIFIED_TEST_ONLY",
    "INPUT_REJECTED",
    "DER_REJECTED",
    "REQUEST_REJECTED",
    "TIME_REJECTED",
    "ACCURACY_REJECTED",
    "SIGNATURE_CHAIN_ESS_EKU_REJECTED",
    "SIGNER_REJECTED",
    "REVOCATION_REJECTED",
    "FLAGS_REJECTED",
)


@dataclass(frozen=True)
class Rfc3161TestResult:
    status: str
    gen_time_us: int
    accuracy_us: int
    evidence_class: str = field(default="CANDIDATE_TEST_EVIDENCE_ONLY", init=False)
    operational_use_approved: bool = field(default=False, init=False)
    machine_time_origin_proven: bool = field(default=False, init=False)
    quorum_countable: bool = field(default=False, init=False)


class Rfc3161QualificationProbe:
    def __init__(self, library):
        if type(library) is not CandidateLibrary:
            raise QualificationError("RFC3161_NATIVE_LIBRARY_ABI_REQUIRED")
        self.library = library
        for name, expected, result in (
            ("cqual_abi_version", 1, c.c_uint32),
            ("cqual_openssl_version", OPENSSL_VERSION, c.c_uint64),
            ("cqual_required_ts_flags", REQUIRED_FLAGS, c.c_uint32),
        ):
            if library.call(name, (), result) != expected:
                raise QualificationError("RFC3161_ABI_OR_VERSION_MISMATCH")

    def verify(
        self,
        request,
        response,
        root,
        crls,
        imprint,
        nonce,
        policy,
        signer_sha256,
        *,
        as_of_us,
        max_accuracy_us,
        asserted_flags=REQUIRED_FLAGS,
    ):
        blobs = (request, response, root, crls, imprint, nonce, signer_sha256)
        if any(type(x) is not bytes or not 1 <= len(x) <= 4 * 1024 * 1024 for x in blobs):
            raise QualificationError("RFC3161_EXACT_BOUNDED_BYTES")
        if len(imprint) != 32 or len(signer_sha256) != 32 or len(nonce) > 32 or nonce[0] == 0:
            raise QualificationError("RFC3161_INPUT_LENGTH")
        if type(policy) is not str or not 1 <= len(policy) <= 128 or any(x not in "0123456789." for x in policy):
            raise QualificationError("RFC3161_POLICY")
        if any(type(x) is not int or not 0 <= x < 2**63 for x in (as_of_us, max_accuracy_us)):
            raise QualificationError("RFC3161_EXPLICIT_TIME")
        if type(asserted_flags) is not int or asserted_flags != REQUIRED_FLAGS:
            raise QualificationError("RFC3161_SIGNATURE_VERIFICATION_REQUIRED")
        arguments, types = [], []
        for blob in (request, response, root, crls, imprint, nonce):
            arguments.extend((blob, len(blob)))
            types.extend((c.c_char_p, c.c_size_t))
        arguments.extend(
            (policy.encode("ascii"), signer_sha256, len(signer_sha256), as_of_us, max_accuracy_us, asserted_flags)
        )
        types.extend((c.c_char_p, c.c_char_p, c.c_size_t, c.c_int64, c.c_int64, c.c_uint32))
        output = (c.c_int64 * 2)()
        arguments.append(output)
        types.append(c.POINTER(c.c_int64))
        status = self.library.call("cqual_verify_rfc3161", tuple(types), c.c_int, *arguments)
        if type(status) is not int or not 0 <= status < len(STATUSES):
            raise QualificationError("RFC3161_STATUS_OUT_OF_INVENTORY")
        if status and tuple(output) != (0, 0):
            raise QualificationError("RFC3161_FAILURE_OUTPUT")
        return Rfc3161TestResult(STATUSES[status], output[0], output[1])
