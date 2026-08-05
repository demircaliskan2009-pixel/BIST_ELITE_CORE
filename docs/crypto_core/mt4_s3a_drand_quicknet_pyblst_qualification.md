# MT4-S3A — Drand Quicknet BLS dependency and fixture qualification

**Status: `QUALIFIED_CANDIDATE_NOT_ADMITTED`.**

This document records a *qualification*, not an admission. Nothing here selects an MT-4 verifier
profile, admits a dependency profile, admits a fixture corpus, approves a provider operationally,
proves machine time or a timestamp origin, makes a proof verified, makes a source quorum-countable,
or promotes readiness or a connector. A separate authorization and design step is required before any
of that, and before any production BLS verification code is written.

Everything below was produced by executing commands and reading primary sources on 2026-08-05. No
load-bearing fact in this document comes from a secondary source, from recollection, or from a model
prior.

---

## 1. Scope and non-claims

| Question | Answer |
|---|---|
| Is a production BLS verifier implemented? | No. |
| Is `pyblst` a project runtime dependency? | No. Absent from `pyproject.toml` and `requirements.txt`; not importable in the repository `.venv`. |
| Does any product module import `pyblst`? | No — proven by a permanent test that scans all of `src/crypto_core`. |
| Does any permanent test reach the network? | No. |
| Does any permanent test require `pyblst` or Go? | No. |
| Is a Drand round admitted as a machine-time origin? | No. |
| Are readiness/connector projections changed? | No — proven by a permanent test. |

`scripts/crypto_core/qualify_drand_quicknet_pyblst.py` is a qualification harness. It performs no
acquisition and has no network, clock, filesystem-discovery or environment surface; every input is
supplied explicitly by the caller. `pyblst` is imported lazily inside the verification entry point, so
importing the module never requires the candidate dependency.

---

## 2. Chain profile, reverified from primary sources

Three independent primary sources were required to agree before any value below was recorded: the
official drand v2.1.6 Go source, the live official HTTP API, and the executed official Go reference
harness.

| Field | Value |
|---|---|
| Beacon id | `quicknet` |
| Chain hash | `52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971` |
| Scheme id | `bls-unchained-g1-rfc9380` |
| Key group (public key) | G2, 96 bytes compressed |
| Signature group | G1, 48 bytes compressed |
| DST | `BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_` (43 bytes) |
| Signed message | `sha256(round.to_bytes(8, "big", signed=False))` |
| Randomness | `sha256(signature_bytes)` |
| Genesis time | `1692803367` |
| Period | `3` seconds |
| Round time | `genesis + (round - 1) * period` — a pure formula, never an ambient clock |

Source pin for the scheme definition: `github.com/drand/drand/v2@v2.1.6/crypto/schemes.go`,
sha256 `58f32452ce9e38e9f25d8692baa1c51b9cfac0167d899aff44cbe70c11a04629`, 14359 bytes. It defines
`SigsOnG1ID = "bls-unchained-g1-rfc9380"`, key group G2, signature group G1, the DST above,
`DigestFunc` as sha256 over the big-endian round, and `RandomnessFromSignature(sig) = sha256(sig)`.

The orientation matters and is easy to get backwards: for this scheme the **public key is on G2 and
the signature is on G1**, which is the reverse of the older chained drand schemes.

---

## 3. Candidate dependency profile — `D-DEP-DRAND-PYBLST-0.3.15-CANDIDATE.v1`

| Artifact | sha256 | Bytes |
|---|---|---|
| `pyblst-0.3.15-cp312-cp312-win_amd64.whl` | `0c2e1f73a4739e9c5c000f00e362d6abe8cd405ec4b94a7db509ef546033999a` | 188331 |
| `pyblst-0.3.15.tar.gz` | `258831210c069ece6d9894bffbe8013834f094d874f30070a4ad8d5a0e317c08` | 12187 |
| `pyblst/pyblst.cp312-win_amd64.pyd` (from the wheel) | `9fddfae2d226e61f40bb3b19584787d196119a5a297ac566027c5923223d8862` | — |
| `LICENSE.txt` (sdist) | `e611139381c1d1167bf2e377c19e668e596f9a42416184ed9a1c1299e24d4dc7` | 1053 |
| `LICENSE.txt` (wheel `dist-info/licenses/`) | `b672dfe9177a29fe44488d5eddfd2cea96535cf99caf729f1921668f35dd1d73` | 1059 |

Both distribution hashes match the controller-supplied input values exactly.

Composition: a PyO3 (0.26.0) binding over upstream `blst`, pinned at **0.3.16**.

### 3.1 Findings that must survive into any future admission decision

**F1 — declared version contradiction (unresolved).** The distribution metadata says `0.3.15`, but
`Cargo.toml` inside the sdist declares `version = "0.3.14"`, and `Cargo.lock` agrees with `0.3.14`.
This is a real, reproducible inconsistency in the upstream release, not an observation error. It is
recorded rather than resolved; an admission decision must not treat the distribution version as a
verified build identity.

**F2 — license resolution is weak.** `LICENSE.txt` contains MIT-style text, but the PyPI `info.license`
field is `None` and there is no SPDX license classifier. The license is *legible* but not
*machine-declared*. Recorded as
`MIT_TEXT_IN_LICENSE_TXT_NO_SPDX_CLASSIFIER_AND_NULL_PYPI_LICENSE_FIELD`.

**F3 — single-maintainer supply chain.** The package has one maintainer. This is a supply-chain
concentration risk for a cryptographic verification boundary and must be weighed at admission time.

**F4 — no high-level verification API.** `pyblst` exposes only primitives: `BlstP1Element`,
`BlstP2Element`, `BlstFP12Element`, `miller_loop`, `final_verify`. There is no signature-verify
function. Any consumer must assemble the pairing check itself, which is where the next finding bites.

**F5 (critical) — the `hash_to_group` argument order is the reverse of its parameter names.**
`pyblst` 0.3.15 declares `hash_to_group(arg1, arg2)` with internal variable names `dst` / `msg`, but
forwards them positionally to `blst_hash_to_g1(out, msg, msg_len, DST, DST_len, aug, aug_len)`. The
**true** call order is therefore `(message, dst)`. Calling it in the documented-name order does not
error — it silently produces a different, self-consistent curve point that never verifies.

This was proven three independent ways:

1. Only `(msg, dst)` reproduces a verifying pairing for the official round-42 beacon; the
   name-ordered call fails.
2. The internal `> 255` length guard rejects a 300-byte value passed as `arg2`.
3. That same guard *accepts* a 300-byte value passed as `arg1`.

Guard (2) and (3) together show the length-bounded parameter is the second one — i.e. the DST — which
means the first parameter is the message. This is a latent correctness trap for any future
implementation and is the single most important output of this qualification.

**F6 — subgroup checks are performed, infinity is not rejected.** `uncompress` performs subgroup
checks (`blst_p1_in_g1` / `blst_p2_in_g2`) and enforces exact 48/96 byte lengths, but it accepts the
canonical encoding of the point at infinity. A consumer **must** reject infinity itself, before any
pairing work. The qualification harness does exactly that, and a permanent test pins the behaviour.

---

## 4. Official reference cross-check

A Go harness was built against the official `github.com/drand/drand/v2` v2.1.6 `crypto` package
(`go.sum` `h1:QpQ6FPy5JMPRTSFvD9HtqDRse/t9dQhDZj7hNMCjM6w=`) using the pinned toolchain
`go1.26.5 windows/amd64`. It calls only official API (`SchemeFromName`, `DigestBeacon`,
`VerifyBeacon`, `RandomnessFromSignature`) — no handwritten re-implementation of the verification
algorithm. It was executed twice with identical output.

A 25-case Python harness was executed twice against `pyblst` 0.3.15 in an isolated virtual
environment containing only that package, installed with `--no-index --no-deps`.

Agreement on every compared case: **exact**.

Cross-checked values for round 42:

| Value | Result |
|---|---|
| Message digest | `a6bb133cb1e3638ad7b8a3ff0539668e9e56f9b850ef1b2a810f5422eaa6c323` |
| Randomness | `8ada64bae5c6c0f5540a6a13af56e663240edfbd2c76ac6a8f27671eb7259ce3` |
| Round time | `1692803490` |
| Verification | passes under both the official Go reference and the candidate dependency |

---

## 5. Causal tracks

Each track states the exact defect it would catch. A track is only listed as demonstrated where a
mutation was actually executed and actually changed the outcome.

| Track | Injected defect | Observed outcome |
|---|---|---|
| Endianness | round encoded little-endian | digest differs; verification fails |
| Pre-hash | raw 8-byte round used as the message, no sha256 | verification fails |
| DST | G2 tag substituted for the G1 tag | `dst_mismatch`; with the guard bypassed, verification fails |
| Randomness | sha256 taken over anything but the exact 48 signature bytes | `randomness_mismatch` |
| Round zero | round 0 | `round_invalid`, rejected before any curve work |
| Signature length | 47 and 49 bytes | `signature_encoding_invalid` |
| Public key length | 95 and 97 bytes | `public_key_encoding_invalid` |
| Infinity | canonical compressed G1/G2 infinity | `point_at_infinity_rejected`, before any pairing |
| Profile binding | chain hash replaced with 32 zero bytes | `chain_profile_binding_invalid` |
| Manifest widening | a fixture id added, removed or reordered | inventory test fails |

The `hash_to_group` order trap (F5) is itself the result of the DST/message track: the initial
positive case failed with `SIGNATURE_VERIFICATION_FAILED` until the true argument order was
established, which is how the finding surfaced.

---

## 6. Fixture corpus — `FX-DRAND-QUICKNET-RFC9380-QUALIFICATION.v1`

Recorded in `tests/crypto_core/fixtures/drand_quicknet_rfc9380_qualification_v1.json`: 3 positive,
23 negative, 2 blocked. Every admitted fixture declares its provenance; the permanent test rejects
any provenance outside the admissible set.

Positive fixtures come from the official drand HTTP API v2, pinned by URL and by the sha256 of the
raw response body:

- chain info — `ff9887bdaa43734aa86582837ef43ba1ee1b14d3bd841d5535f94651b85ab7d3`
- round 42 — `b7f86008c4b7ddffe6b8cf65371c801973360f4b13f107a9c3bf1460a6b1f44e`

### 6.1 Blocked fixtures — no bytes were invented

Two negative fixtures could not be produced from an admissible primary source and are recorded as
`FIXTURE_ADMISSION_BLOCKED` with reason `fixture_provenance_invalid`:

- `blocked_subgroup_invalid_g1_point` — a subgroup-invalid G1 point with primary-source provenance
  was not obtained.
- `blocked_non_canonical_encoding_point` — a non-canonical (unreduced field element) compressed
  encoding with primary-source provenance was not obtained.

The corresponding code paths exist and are exercised by deterministically derived inputs, but no
dedicated normative vector is admitted for them. **Bytes were deliberately not fabricated.** A future
admission step must source these from a normative test vector set.

---

## 7. Known limitations disclosed honestly

- **HTTP status and content type were not captured.** `Invoke-WebRequest` was unavailable in the
  non-interactive session and `System.Net.Http.HttpClient` could not be loaded, so the fixtures were
  downloaded with `System.Net.WebClient.DownloadFile`, which returns only the body. The response
  bodies are hash-pinned and their content was cross-verified against the official Go reference, but
  the transport metadata is `NOT_CAPTURED`.
- **P3 (transient, self-resolved).** The first Go build failed with `asm.exe: Access is denied`, an
  antivirus lock on a freshly extracted binary. It cleared without intervention. Recorded because a
  build failure adjacent to a cryptographic qualification should never be silently dropped.
- **Windows/CPython 3.12 only.** The wheel qualified here is `cp312-win_amd64`. No claim is made for
  any other platform, architecture or Python version.
- **F1 is unresolved**, not waived.

---

## 8. Decision

`DEPENDENCY_QUALIFICATION: PASS_CANDIDATE_ONLY` — the candidate dependency reproduces the official
drand reference exactly on every compared case, fails closed on every required negative, and its one
critical usage trap (F5) has been identified and documented.

`DEPENDENCY_ADMITTED: NO` — F1 (version contradiction), F2 (weak license declaration), F3
(single-maintainer supply chain) and the two blocked fixtures are open. Admission requires a separate
authorization, and for a cryptographic verification boundary, an independent Class-C audit.

**Next safe action:** none in this slice. MT4-S3B (verifier profile selection) must not begin until
the admission decision above is taken by the controller under separate authorization.
