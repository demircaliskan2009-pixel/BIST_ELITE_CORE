"""Generate signed synthetic vectors inside the protected source-built test DLL.

No CLI process, file-based private key or ambient clock is used. Test roots and
signatures are not provider evidence. Only public synthetic DER leaves native
memory; no key is printed, persisted or uploaded.
"""

from __future__ import annotations

import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path

from scripts.crypto_core.qualification.c_native_formats import QualificationError
from scripts.crypto_core.qualification.c_native_loader import CandidateLibrary
from scripts.crypto_core.qualification.c_rfc3161_probe import EXPORTS

GENERATOR = "cqual_generate_test_vectors"
NAMES = (
    "request.der",
    "response.der",
    "root.der",
    "good-crl.der",
    "revoked-crl.der",
    "no-accuracy.der",
    "tsa.der",
    "no-ess.der",
    "wrong-policy.der",
    "expired-signer.der",
    "untrusted-root.der",
)


def generate(receipt_path, output):
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    if (
        receipt.get("status") != "BUILT_NOT_QUALIFIED_NOT_ADMITTED"
        or receipt.get("evidence_class") != "CANDIDATE_TEST_EVIDENCE_ONLY"
    ):
        raise QualificationError("TEST_BUILD_RECEIPT")
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    record = receipt["artifacts"]["openssl"]
    content = Path(record["path"]).read_bytes()
    with CandidateLibrary(content, record["sha256"], EXPORTS + (GENERATOR,), staging_root=output) as loaded:
        buffer, size = c.create_string_buffer(1024 * 1024), c.c_size_t()
        if (
            loaded.call(
                GENERATOR, (c.c_char_p, c.c_size_t, c.POINTER(c.c_size_t)), c.c_int, buffer, len(buffer), c.byref(size)
            )
            != 1
        ):
            raise QualificationError("SYNTHETIC_VECTOR_GENERATION")
        if not 0 < size.value <= len(buffer):
            raise QualificationError("SYNTHETIC_VECTOR_SIZE")
        data = buffer.raw[: size.value]
        baseline = loaded.baseline
    files, offset = {}, 0
    for name in NAMES:
        if offset + 4 > len(data):
            raise QualificationError("SYNTHETIC_VECTOR_FRAME")
        length = int.from_bytes(data[offset : offset + 4], "big")
        offset += 4
        if not 0 < length <= len(data) - offset:
            raise QualificationError("SYNTHETIC_VECTOR_FRAME")
        files[name] = data[offset : offset + length]
        offset += length
    if offset != len(data):
        raise QualificationError("SYNTHETIC_VECTOR_TRAILING_DATA")
    for name, payload in files.items():
        (output / name).write_bytes(payload)
    packet = {
        "evidence_class": "SYNTHETIC_TEST_ONLY",
        "operational_use_approved": False,
        "imprint": (b"i" * 32).hex(),
        "nonce": "0123456789abcdef",
        "policy": "1.2.3.4.5",
        "signer_sha256": hashlib.sha256(files["tsa.der"]).hexdigest(),
        "gen_time_us": 1800000000 * 1000000,
        "as_of_us": 1800000060 * 1000000,
        "max_accuracy_us": 1100010,
        "generation_command": "cqual_generate_test_vectors inside protected candidate DLL; fixed synthetic time and nonce",
        "os_dependency_baseline": baseline,
        "files": {
            name: {"path": str(output / name), "sha256": hashlib.sha256(payload).hexdigest()}
            for name, payload in files.items()
        },
    }
    (output / "vectors.json").write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    return packet


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    generate(args.receipt, args.output)
