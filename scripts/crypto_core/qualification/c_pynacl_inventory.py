"""Observe the existing PyNaCl/cffi native boundary without importing native code.

RECORD consistency is installation evidence, not authenticated wheel provenance,
not libsodium version/build proof and never operational admission.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.metadata
import io
import json


def inventory():
    packages = []
    for name in ("PyNaCl", "cffi", "pycparser"):
        dist = importlib.metadata.distribution(name)
        text = dist.read_text("RECORD")
        records, mismatch = [], []
        for path, digest, size in csv.reader(io.StringIO(text or "")):
            if not digest:
                continue
            algorithm, encoded = digest.split("=", 1)
            file = dist.locate_file(path)
            if algorithm != "sha256" or not file.is_file():
                mismatch.append(path)
                continue
            content = file.read_bytes()
            actual = hashlib.sha256(content).digest()
            if base64.urlsafe_b64encode(actual).rstrip(b"=").decode("ascii") != encoded or str(len(content)) != size:
                mismatch.append(path)
            if path.lower().endswith((".pyd", ".so", ".dll")):
                records.append({"path": str(file), "sha256": actual.hex(), "bytes": len(content)})
        packages.append(
            {
                "name": name,
                "version": dist.version,
                "record_present": text is not None,
                "record_mismatches": mismatch,
                "native_objects": records,
            }
        )
    return {
        "evidence_class": "CANDIDATE_TEST_EVIDENCE_ONLY",
        "packages": packages,
        "pynacl_pin_matches": packages[0]["version"] == "1.6.2",
        "libsodium_build_identity": "UNPROVEN_REQUIRES_AUTHENTICATED_WHEEL_BUILD_EVIDENCE",
        "dependency_admission": False,
        "operational_use_approved": False,
    }


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2, sort_keys=True))
