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
- Only the stable `blst.h` surface is used: the shim directly includes `blst.h` alone and makes no
  direct call to any auxiliary API, so no experimental interface carries a load-bearing
  qualification claim. The pinned `blst.h` itself ends with an `#include` of `blst_aux.h`, so those
  declarations are transitively visible — the claim is about what this project includes and calls,
  not about header reachability.
- `ctypes` avoids depending on an upstream Python extension ABI, which keeps the Python 3.8 floor
  reachable without a compiled Python module.

Rejected or deferred alternatives (recorded so the choice is auditable, not for convenience):

- **third-party `pyblst`** — controller-rejected on Python floor and publication/provenance grounds.
- **upstream SWIG proof-of-concept** — upstream ships it as a proof of concept, not a maintained
  binding; it is not an admitted distribution.
- **Rust/PyO3 adapter** — adds a second toolchain and a second supply chain for no qualification
  benefit at this stage.

## Quicknet contract (fixed, never caller-selectable)

```text
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

## Lane A negative matrix and its two distinct claims

Two things must never be conflated:

- **SOURCE-PINNED VECTOR AVAILABILITY** — the official low-order vectors exist at an exact upstream
  path and commit, and the workflow extracts them by exact identifier. This is a *provenance* claim
  and it is true today.
- **CI-EXECUTED QUALIFICATION RESULT** — those vectors were actually pushed through the shim on a
  runner and produced the exact expected bounded statuses. This is an *execution* claim and it is
  `PENDING_CI`. It is not asserted anywhere in this repository.

Authority for the negative matrix is `bindings/python/run.me` at commit
`54e6e55674722fc2797ebb4bbb71b26d881eb4b8` (Apache-2.0), which carries the low-order families
`p11`, `p10177`, `p859267` (G1) and `p13`, `p23`, `p2713` (G2) and itself proves `in_group() == false`
for each. Vectors are parsed at CI runtime by an identifier-anchored strict parser and are **not**
copied into this repository. The parser fails closed if an identifier is absent, duplicated, or its
literal is the wrong size, and it re-proves the pinned upstream commit before trusting the file.

| Case | Required bounded status |
| --- | --- |
| official G1 low-order (`p11`, `p10177`, `p859267`) | `SIG_NOT_IN_GROUP` |
| official G2 low-order (`p13`, `p23`, `p2713`) | `PK_NOT_IN_GROUP` |
| malformed G1 | `SIG_BAD_ENCODING` |
| malformed G2 | `PK_BAD_ENCODING` |
| canonical G1 infinity | `SIG_INFINITY` |
| canonical G2 infinity | `PK_INFINITY` |
| truncated / overlong G1, G2, digest | `BAD_LENGTH` |

`BAD_ENCODING`, `INFINITY`, `NOT_IN_GROUP` and `BAD_LENGTH` stay distinguishable; "rejected" alone is
never accepted as evidence for these cases.

Reaching the **signature** gates requires a public key that genuinely lies in the prime-order
subgroup, because the public key is proven first. That point is the compressed G2 generator, emitted
by a clearly separated qualification-scaffolding entry point that obtains it through the stable
public accessor `blst_p2_affine_generator()`.

The pinned public header (`bindings/blst.h`) declares both the exported `BLS12_381_G2` datum and
`blst_p2_affine_generator()`. This qualification deliberately selects the accessor and does not
directly address the datum, as a project-side encapsulation choice — not because upstream forbids or
fails to support direct use. `src/e2.c` defines the datum as a projective `POINTonE2` and implements
the accessor as an affine cast of it; `src/aggregate.c` also casts the same datum directly in more
than one internal path outside the accessor. So no claim is made that only the accessor performs this
reinterpretation, or that the datum is undeclared, aux-only, experimental, or unsupported.

The scaffolding decodes nothing from a caller, performs no verification and carries no trust
decision; it exists so Lane A never embeds a point literal nor borrows Lane-B production bytes.

### `SIG_NOT_IN_GROUP` has two bounded causal routes

Pinned blst does not decide G1 subgroup membership in only one place, so the qualification ABI must
not pretend it does:

| Route | Mechanism | Status |
| --- | --- | --- |
| A | `blst_p1_uncompress` itself returns `BLST_POINT_NOT_IN_GROUP` | `SIG_NOT_IN_GROUP` |
| B | decode returns `BLST_SUCCESS`, then the explicit `blst_p1_affine_in_g1` gate rejects | `SIG_NOT_IN_GROUP` |

Route A exists because `src/e1.c` `POINTonE1_Uncompress_Z` ends with:

```text
/* (0,±2) is not in group, but application might want to ignore? */
return vec_is_zero(out->X, sizeof(out->X)) ? BLST_POINT_NOT_IN_GROUP : BLST_SUCCESS;
```

The decoder masks the three flag bits out of X, so a compressed input of `0x80` followed by 47 zero
bytes decodes to **X = 0**. That is a genuine curve point — `Y² = 0³ + 4`, so `Y = ±2` — which
reconstructs successfully and is then rejected by the decoder on *subgroup* grounds. `0xA0` selects
the opposite Y sign and behaves identically.

Collapsing that into `SIG_BAD_ENCODING` would misreport a subgroup rejection as a malformed input,
so the shim captures the exact `BLST_ERROR` and maps only `BLST_POINT_NOT_IN_GROUP` to
`SIG_NOT_IN_GROUP`. **Malformed and not-on-curve compressed signatures remain `SIG_BAD_ENCODING`.**

This edge is executed natively on both platforms as `g1_decode_time_not_in_group_x0`, emitting
`LANE_A_G1_DECODE_SUBGROUP_RESULT=SIG_NOT_IN_GROUP`.

**Provenance is distinct from the low-order family.** The six `p11`/`p10177`/`p859267` /
`p13`/`p23`/`p2713` vectors come from `bindings/python/run.me`. The X=0 edge does **not** — its
authority is `src/e1.c` implementation semantics at the same pinned commit, and it is never labelled
a `run.me` vector.

**G2 is deliberately not symmetric.** `src/e2.c` contains no decode-time `BLST_POINT_NOT_IN_GROUP`
return at this commit, so every G2 decode failure really is an encoding/curve failure and G2 subgroup
membership stays the responsibility of the explicit `blst_p2_affine_in_g2` gate. No symmetric mapping
is invented without pinned-source evidence.

**Non-canonical encodings are NOT wired.** No confirmed upstream non-canonical compressed-input
vector class was established at the pinned commit, and none is invented here. The shim retains its
recompress-and-compare gate and the `PK_NON_CANONICAL` / `SIG_NON_CANONICAL` statuses, which are
covered structurally by the permanent tests only.

## Drand v2 contract and the Quicknet root of trust

Lane B talks to the **current Drand v2** API and uses v2-native field names only. Two separate
contracts apply here:

```text
generic /v2/chains/<chain_hash>/info schema
  required: public_key, period, genesis_time, scheme
  optional: genesis_seed, chain_hash, beacon_id

this Quicknet qualification's root-binding policy
  required: public_key, period, genesis_time, genesis_seed, scheme

round /v2/chains/<chain_hash>/rounds/<round>
  required: round, signature
```

The official generic Drand v2 schema makes `genesis_seed` optional. This qualification nevertheless
fails closed when Quicknet `genesis_seed` is missing or empty, because canonical root recomputation
requires it. `chain_hash` is schema-optional and is only a self-reported cross-check, never the
trust root. `beacon_id` is also schema-optional; this qualification independently pins Quicknet's
non-default `quicknet` beacon ID for canonical-root recomputation and cross-checks a returned value
if present.

The legacy names `hash`, `groupHash`, `schemeID` and `metadata.beaconID` are deliberately rejected
by this qualification's project-side strict v2 parser. That is a project policy, not an assertion
about upstream parser capability: upstream Drand's `Info.UnmarshalJSON` retains compatibility for
legacy `schemeID`, `groupHash`, and `metadata.beaconID` aliases.

**Why renaming the field was not enough.** The relay that reports the chain identity is the same
relay that supplies the public key used for BLS verification. Trusting `chain_hash` because that
response said so is circular: an attacker controlling the response could supply a matching pair.
Lane B therefore recomputes the canonical Drand chain-info hash over the returned material and
requires equality with the project-pinned Quicknet root **before** the key may be used:

```text
sha256( uint32_be(period)
      || int64_be(genesis_time)
      || public_key_bytes
      || genesis_seed_bytes
      || beacon_id_bytes_if_non_default )
      == 52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971
```

The canonical-hash provenance is [`drand/drand`](https://github.com/drand/drand), commit
[`2363f3b9ba5fd6f14e0b84a096b248479790d75d`](https://github.com/drand/drand/blob/2363f3b9ba5fd6f14e0b84a096b248479790d75d/common/chain/info.go),
`common/chain/info.go`, `Info.Hash`. Its algorithm is `sha256(uint32_be(period_seconds) ||
int64_be(genesis_time) || public_key_marshaled_bytes || genesis_seed_bytes ||
non_default_beacon_id_bytes)`. This pinned source is provenance evidence for this qualification
contract only; it is not a dependency admission, provider approval, or future API guarantee.

Quicknet's beacon ID `quicknet` is non-default, so it participates in the hash. HTTPS transport and
endpoint path routing are **not** treated as the cryptographic root. Only after this binding passes
is the fetched key handed to the shim.

Current v2 round data does **not** define a required `randomness` field, and the official Quicknet
round-42 response carries only `round` and `signature`. This qualification therefore does not require
it. If an extra `randomness` value is present it is checked defensively (strict 32-byte hex equal to
`SHA256(signature)`) and a mismatch fails closed — a project-side consistency rule, not a v2 schema
requirement. Quicknet is unchained, so a non-empty `previous_signature` fails closed.

## Exact-head qualification provenance

Pull-request runs check out `github.event.pull_request.head.sha` explicitly, not GitHub's synthetic
`refs/pull/<n>/merge` commit, and the job asserts at runtime that `git rev-parse HEAD` equals that
expected SHA before any build or qualification step runs. Qualification evidence must describe code
that actually exists on the branch under audit. Mismatch fails closed with
`QUALIFICATION_SOURCE_HEAD_MISMATCH`; success emits `QUALIFICATION_EXACT_HEAD=PASS`.

## Pre-repair PR run — what it did and did not establish

The first PR run of this workflow produced, on **both** `windows-2022` and `ubuntu-22.04`:

```text
normal ci                                    SUCCESS
Python 3.8 provisioning                      PASS
pinned blst checkout and build               PASS
native shim build and load                   PASS
Lane A structural negative matrix            PASS
Lane A official upstream low-order subgroup  PASS
Lane B                                       FAILED
```

Lane B failed **before reaching any real BLS verification**, because it used the legacy v1 `hash`
field against the v2 endpoint. That run therefore did **not** establish `REAL_QUICKNET_VERIFY`, nor
full Windows or Linux qualification. It did establish that the toolchain, the pinned upstream build,
the native ABI and the entire Lane-A matrix work on both platforms.

The repaired workflow has not yet been observed by the controller. No repaired-run success is
claimed here.

## Cross-platform evidence

The development workstation has no native toolchain (no MSVC/GCC/Clang, no Rust, no SWIG, no Python
3.8), so no local build or execution proof is possible and none is claimed. Execution evidence is
produced exclusively by `.github/workflows/crypto_core_mt4_s3a_blst_qualification.yml` on fixed
hosted runner families (`windows-2022`, `ubuntu-22.04`) with Python 3.8 provisioned explicitly and
the upstream commit re-proven at runtime.

```text
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

```text
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
