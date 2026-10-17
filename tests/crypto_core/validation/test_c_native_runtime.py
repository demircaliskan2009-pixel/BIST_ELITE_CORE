"""Real native tests, requiring a source-linked build and synthetic signed corpus.

Missing material is BLOCKED, never a fabricated PASS. CI's required-native mode
turns unavailable material into failure. No real source/proof is admitted.
"""

from __future__ import annotations

import ctypes as c
import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.crypto_core.qualification.c_native_formats import QualificationError
from scripts.crypto_core.qualification.c_native_loader import CandidateLibrary
from scripts.crypto_core.qualification.c_native_windows import windows_path
from scripts.crypto_core.qualification.c_rfc3161_probe import EXPORTS, Rfc3161QualificationProbe


@pytest.fixture(scope="module")
def material():
    receipt_path, vector_path = os.environ.get("C_NATIVE_BUILD_RECEIPT"), os.environ.get("C_RFC3161_VECTORS")
    if not receipt_path or not vector_path:
        if os.environ.get("C_REQUIRE_NATIVE") == "1":
            pytest.fail("mandatory native build or vector packet missing")
        pytest.skip("BLOCKED: exact source-built binaries and signed synthetic vectors unavailable")
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    vectors = json.loads(Path(vector_path).read_text(encoding="utf-8"))
    assert receipt["evidence_class"] == "CANDIDATE_TEST_EVIDENCE_ONLY"
    assert receipt["status"] == "BUILT_NOT_QUALIFIED_NOT_ADMITTED"
    assert vectors["evidence_class"] == "SYNTHETIC_TEST_ONLY" and vectors["operational_use_approved"] is False
    files = {}
    for name, record in vectors["files"].items():
        files[name] = Path(record["path"]).read_bytes()
        assert hashlib.sha256(files[name]).hexdigest() == record["sha256"]
    return receipt, vectors, files


@pytest.fixture(scope="module")
def library(material, tmp_path_factory):
    receipt, _, _ = material
    record = receipt["artifacts"]["openssl"]
    with CandidateLibrary(
        Path(record["path"]).read_bytes(),
        record["sha256"],
        EXPORTS,
        staging_root=tmp_path_factory.mktemp("native-rfc3161"),
    ) as loaded:
        yield loaded


def verify(library, material, case="good", **overrides):
    _, v, f = material
    arguments = dict(
        request=f["request.der"],
        response=f["response.der"],
        root=f["root.der"],
        crls=f["good-crl.der"],
        imprint=bytes.fromhex(v["imprint"]),
        nonce=bytes.fromhex(v["nonce"]),
        policy=v["policy"],
        signer_sha256=bytes.fromhex(v["signer_sha256"]),
        as_of_us=v["as_of_us"],
        max_accuracy_us=v["max_accuracy_us"],
    )
    if case == "tampered-signature":
        arguments["response"] = f["response.der"][:-1] + bytes((f["response.der"][-1] ^ 1,))
    elif case == "revoked-authority":
        arguments["crls"] = f["revoked-crl.der"]
    elif case == "crl-signature":
        arguments["crls"] = f["good-crl.der"][:-1] + bytes((f["good-crl.der"][-1] ^ 1,))
    elif case == "missing-accuracy":
        arguments["response"] = f["no-accuracy.der"]
    elif case == "missing-ess":
        arguments["response"] = f["no-ess.der"]
    elif case == "wrong-tsa-policy":
        arguments["response"] = f["wrong-policy.der"]
    elif case == "historical-validity":
        arguments["response"] = f["expired-signer.der"]
    elif case == "untrusted-root":
        arguments["root"] = f["untrusted-root.der"]
    arguments.update(overrides)
    return Rfc3161QualificationProbe(library).verify(**arguments)


def test_native_valid_signature_chain_eku_ess_policy_imprint_nonce_accuracy(library, material):
    first, second = verify(library, material), verify(library, material)
    assert first == second
    assert first.status == "VERIFIED_TEST_ONLY"
    assert first.gen_time_us == material[1]["gen_time_us"]
    assert first.accuracy_us == material[1]["max_accuracy_us"]
    assert not first.machine_time_origin_proven and not first.operational_use_approved


@pytest.mark.parametrize(
    "case,status",
    [
        ("tampered-signature", "SIGNATURE_CHAIN_ESS_EKU_REJECTED"),
        ("revoked-authority", "REVOCATION_REJECTED"),
        ("crl-signature", "REVOCATION_REJECTED"),
        ("missing-accuracy", "ACCURACY_REJECTED"),
        ("missing-ess", "SIGNATURE_CHAIN_ESS_EKU_REJECTED"),
        ("wrong-tsa-policy", "SIGNATURE_CHAIN_ESS_EKU_REJECTED"),
        ("historical-validity", "SIGNATURE_CHAIN_ESS_EKU_REJECTED"),
        ("untrusted-root", "SIGNATURE_CHAIN_ESS_EKU_REJECTED"),
    ],
)
def test_native_signed_evidence_negatives(library, material, case, status):
    assert verify(library, material, case).status == status


@pytest.mark.parametrize(
    "field,value,status",
    [
        ("signer_sha256", b"x" * 32, "SIGNER_REJECTED"),
        ("policy", "1.2.3.4.6", "REQUEST_REJECTED"),
        ("imprint", b"x" * 32, "REQUEST_REJECTED"),
        ("nonce", b"x" * 16, "REQUEST_REJECTED"),
        ("as_of_us", 1, "TIME_REJECTED"),
        ("max_accuracy_us", 0, "ACCURACY_REJECTED"),
        ("as_of_us", 2**62, "REVOCATION_REJECTED"),
    ],
    ids=(
        "wrong-signer",
        "wrong-policy",
        "wrong-imprint",
        "wrong-nonce",
        "future-token",
        "accuracy-limit",
        "expired-crl",
    ),
)
def test_native_explicit_bindings(library, material, field, value, status):
    assert verify(library, material, **{field: value}).status == status


def test_native_signature_disabled_path_rejected(library, material):
    with pytest.raises(QualificationError, match="SIGNATURE_VERIFICATION_REQUIRED"):
        verify(library, material, asserted_flags=0)


def test_native_c_signature_disabled_path_rejected(library, material):
    _, v, f = material
    args, types = [], []
    for blob in (
        f["request.der"],
        f["response.der"],
        f["root.der"],
        f["good-crl.der"],
        bytes.fromhex(v["imprint"]),
        bytes.fromhex(v["nonce"]),
    ):
        args.extend((blob, len(blob)))
        types.extend((c.c_char_p, c.c_size_t))
    output = (c.c_int64 * 2)(123, 456)
    args.extend(
        (
            v["policy"].encode("ascii"),
            bytes.fromhex(v["signer_sha256"]),
            32,
            v["as_of_us"],
            v["max_accuracy_us"],
            0,
            output,
        )
    )
    types.extend((c.c_char_p, c.c_char_p, c.c_size_t, c.c_int64, c.c_int64, c.c_uint32, c.POINTER(c.c_int64)))
    assert library.call("cqual_verify_rfc3161", tuple(types), c.c_int, *args) == 9
    assert tuple(output) == (0, 0)


def test_native_protected_object_path_swap_and_parent_rename(library, tmp_path):
    protected = library.object
    if os.name == "nt":
        replacement = tmp_path / "replacement.dll"
        replacement.write_bytes(b"substitution")
        assert not protected.k.MoveFileExW(windows_path(replacement), protected.load_path, 1)
        assert c.get_last_error() in (5, 32)
        assert not protected.k.MoveFileExW(
            windows_path(protected.directory), windows_path(protected.directory.with_name("renamed-directory")), 0
        )
        assert c.get_last_error() in (5, 32)
    else:
        with pytest.raises(OSError):
            os.write(protected.fd, b"mutable-race")
    protected.reprove()


def test_native_modified_artifact_rejected_before_loading(material, tmp_path):
    record = material[0]["artifacts"]["openssl"]
    content = Path(record["path"]).read_bytes()
    modified = content[:-1] + bytes((content[-1] ^ 1,))
    with pytest.raises(QualificationError, match="BINARY_DIGEST_MISMATCH"):
        CandidateLibrary(modified, record["sha256"], EXPORTS, staging_root=tmp_path)


def test_native_blst_abi_and_malformed_signature(material, tmp_path):
    record = material[0]["artifacts"]["blst"]
    exports = ("mt4_s3a_verify_quicknet_bls", "mt4_s3a_qualification_g2_generator_compressed")
    with CandidateLibrary(
        Path(record["path"]).read_bytes(), record["sha256"], exports, staging_root=tmp_path
    ) as loaded:
        key = c.create_string_buffer(96)
        assert loaded.call(exports[1], (c.c_char_p, c.c_size_t), c.c_int, key, 96) == 0
        signature = bytes(48)
        args = (key, 96, signature, 48, bytes(32), 32)
        types = (c.c_char_p, c.c_size_t) * 3
        assert loaded.call(exports[0], types, c.c_int, *args) != 0
