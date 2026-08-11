# MT4-S3A — blst v0.3.17 narrow C-ABI qualification (V2)

Status: **ARCHITECTURE_CANDIDATE**. Cross-platform execution evidence is **PENDING_CI**.

This slice is qualification infrastructure only. It builds nothing into `src/crypto_core`, admits no
dependency, selects no verifier profile, and moves no readiness or connector state. Nothing in this
document may be read as an admission or a promotion.

## The four states this slice deliberately separates

These are distinct gates. Passing an earlier one never implies a later one.

| State | Meaning | Current value |
| --- | --- | --- |
| `ARCHITECTURE_CANDIDATE` | A candidate verification boundary exists and is being qualified in CI. | **this slice** |
| `DEPENDENCY_ADMISSION` | `blst` is an admitted crypto_core dependency with a governed provenance chain. | `false` |
| `VERIFIER_PROFILE_SELECTION` | An MT4 verifier profile is selected and bound to a source. | `false` |
| `READINESS` | Readiness/connector/quorum/proof state moves. | `false` |

A successful qualification run proves only that the candidate boundary **can** verify Quicknet
correctly on the target platforms. It is input to a future controller decision, not the decision.

## Candidate under qualification

A project-owned narrow C ABI over the official upstream C library, loaded from Python with stdlib
`ctypes`.

- Upstream: `supranational/blst`, release `v0.3.17`, commit
  `54e6e55674722fc2797ebb4bbb71b26d881eb4b8`, Apache-2.0.
- Only the stable `blst.h` surface is used. `blst_aux.h` is excluded: no experimental interface may
  carry a load-bearing qualification claim.
- `ctypes` avoids depending on an upstream Python extension ABI, which keeps the Python 3.8 floor
  reachable without a compiled Python module.

Rejected or deferred alternatives (recorded so the choice is auditable, not for convenience):

- **third-party `pyblst`** — controller-rejected on Python floor and publication/provenance grounds.
- **upstream SWIG proof-of-concept** — upstream ships it as a proof of concept, not a maintained
  binding; it is not an admitted distribution.
- **Rust/PyO3 adapter** — adds a second toolchain and a second supply chain for no qualification
  benefit at this stage.

## Quicknet contract (fixed, never caller-selectable)

```
scheme        bls-unchained-g1-rfc9380
curve         BLS12-381
public key    G2, compressed, exactly 96 bytes
signature     G1, compressed, exactly 48 bytes
message       SHA256(uint64_big_endian(round)), exactly 32 bytes
DST           BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_
augmentation  none
chain hash    52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971
```

The DST is a compile-time file-scope constant inside the shim. A caller cannot supply or override
the DST, curve, group orientation, hash mode or augmentation through the ABI.

## Verification sequence

1. NULL and exact-length gates (96 / 48 / 32) before any cryptographic work.
2. `blst_p2_uncompress` — compressed G2 public-key decode.
3. `blst_p2_affine_compress` + `memcmp` — canonical wire-form proof.
4. `blst_p2_affine_is_inf` — reject the G2 identity.
5. `blst_p2_affine_in_g2` — **explicit** G2 subgroup membership, never inferred from the pairing.
6. `blst_p1_uncompress` — compressed G1 signature decode.
7. `blst_p1_affine_compress` + `memcmp` — canonical wire-form proof.
8. `blst_p1_affine_is_inf` — reject the G1 identity.
9. `blst_p1_affine_in_g1` — **explicit** G1 subgroup membership.
10. `blst_core_verify_pk_in_g2` with `hash_or_encode = true`, the fixed Quicknet DST and no
    augmentation.
11. Every failure maps to a bounded status; upstream `BLST_ERROR` values never cross the ABI.

Bounded status inventory: `0 OK`, `1 NULL_INPUT`, `2 BAD_LENGTH`, `3 PK_BAD_ENCODING`,
`4 PK_NON_CANONICAL`, `5 PK_INFINITY`, `6 PK_NOT_IN_GROUP`, `7 SIG_BAD_ENCODING`,
`8 SIG_NON_CANONICAL`, `9 SIG_INFINITY`, `10 SIG_NOT_IN_GROUP`, `11 VERIFY_FAILED`.

## Determinism boundary

The native library is loaded from the filesystem once, during probe construction. That is reported
as `NATIVE_LIBRARY_FILESYSTEM_LOAD_AT_INIT = true` and must never be restated as a per-call
filesystem dependency. A verification call performs no filesystem, network, clock, environment or
randomness access. The committed probe imports no network capability at all, so this is a structural
property of the file rather than a runtime promise.

## Why V2 is dual-lane

Historical V1 (`wip/crypto-core-mt4-s3a-drand-quicknet-qualification`) required that *every committed
raw fixture has explicit reuse/license support*. That rule is respected here, not weakened — but V1
also permanently pins its own fixture inventory and blockers, so it cannot be stretched to cover this
slice as-is. V2 is therefore an explicit new governance contract; V1 remains immutable historical
evidence and is not rewritten.

The problem V2 solves: proving compatibility with a real production beacon does not require
**redistributing** that beacon. Splitting the two removes the licensing question from the repository
entirely instead of assuming a rights grant nobody has proven.

### Lane A — committed offline corpus

May contain only explicitly licensed, hash-pinned upstream material; official blst Apache-2.0 vectors
at the pinned commit; deterministic generated KATs with fully specified derivation; and deterministic
negatives derived from an admitted Lane-A base. Raw production Quicknet response bytes are **not**
admissible unless independent explicit reuse permission is proven — which has not been proven and is
not assumed. Generated bytes are never labelled `UPSTREAM_LIBRARY_VECTOR`.

### Lane B — transient production compatibility

A real public Quicknet beacon may be used **during the qualification workflow only**, in runner
temporary storage and process memory. Raw response and signature bytes are never committed, never
uploaded as an artifact, and never printed. Persistent evidence is limited to: source endpoint
identity, chain hash, round number, SHA-256 of the raw signature, SHA-256 of the public key, the
verification result, the pinned verifier architecture identity, and a retrieval timestamp as
qualification metadata.

Lane B is evidence only. It does **not** admit provider reachability, prove machine time or timestamp
origin, make a provider operationally approved, make a source quorum-countable, or promote readiness
or connectors. One successful run also does not establish network availability as a property.

## Cross-platform evidence

The development workstation has no native toolchain (no MSVC/GCC/Clang, no Rust, no SWIG, no Python
3.8), so no local build or execution proof is possible and none is claimed. Execution evidence is
produced exclusively by `.github/workflows/crypto_core_mt4_s3a_blst_qualification.yml` on fixed
hosted runner families (`windows-2022`, `ubuntu-22.04`) with Python 3.8 provisioned explicitly and
the upstream commit re-proven at runtime.

```
windows_execution_proof  PENDING_CI
linux_execution_proof    PENDING_CI
python38_execution_proof PENDING_CI
```

If Drand is unreachable the workflow fails closed. The evidence requirement is not to be bypassed by
changing the code.

## Provenance chain for a future implementation slice

Designed here, deliberately **not** implemented: `UPSTREAM_REPO`, `UPSTREAM_TAG`, `UPSTREAM_COMMIT`,
`UPSTREAM_LICENSE`, upstream source-tree digest strategy, `COMPILER_ID`, `COMPILER_VERSION`,
`BUILD_FLAGS`, portable mode, target triple, `SHIM_SOURCE_DIGEST`, `OUTPUT_BINARY_SHA256`,
`BUILD_RECIPE_DIGEST`, `CI_WORKFLOW_IDENTITY`.

GitHub artifact attestation should be treated as **OPTIONAL** at qualification stage and
**REQUIRED** at dependency-admission stage. No attestation exists today and none is claimed.

## Files in this slice

```
.github/workflows/crypto_core_mt4_s3a_blst_qualification.yml
scripts/crypto_core/qualification/mt4_s3a_blst_quicknet_shim.c
scripts/crypto_core/qualification/mt4_s3a_blst_quicknet_probe.py
tests/crypto_core/fixtures/mt4_s3a_blst_v0317_qualification_v2.json
tests/crypto_core/validation/test_mt4_s3a_blst_v0317_qualification.py
docs/crypto_core/mt4_s3a_blst_v0317_qualification.md
```

The permanent tests are offline and stdlib-only: they own the committed contract by inspecting these
files, so removing a subgroup gate, widening the ABI, unpinning upstream, admitting a dependency,
promoting readiness or committing raw production bytes fails locally rather than only in CI.
