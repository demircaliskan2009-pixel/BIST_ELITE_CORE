# MT4-S3A — Drand Quicknet BLS dependency and fixture qualification

**Status: `BLOCKED_NOT_QUALIFIED_NOT_ADMITTED`.**

| Decision | Value | Blocker |
|---|---|---|
| `DEPENDENCY_QUALIFICATION` | **BLOCKED** | `package_version_identity_ambiguous` |
| `FIXTURE_QUALIFICATION` | **BLOCKED** | `fixture_license_unresolved` |
| `PACKAGE_SOURCE_CONTRADICTIONS` | `UNRESOLVED_PACKAGE_VERSION_IDENTITY_AMBIGUITY` | — |

Neither qualification passed. The candidate dependency reproduces the official drand reference exactly
on every compared case and fails closed on every required negative — that evidence is real and is
retained below — but exact-evidence requirements that the decision rules make mandatory are not met, so
the decisions are BLOCKED. Useful candidate evidence and a BLOCKED decision are not in conflict.

This document records a *qualification attempt*, not an admission. Nothing here selects an MT-4
verifier profile, admits a dependency profile, admits a fixture corpus, approves a provider
operationally, proves machine time or a timestamp origin, makes a proof verified, makes a source
quorum-countable, or promotes readiness or a connector. A separate authorization and design step is
required before any of that, and before any production BLS verification code is written.

Everything below was produced by executing commands and reading primary sources on 2026-08-05. No
load-bearing fact in this document comes from a secondary source, from recollection, or from a model
prior.

---

## 1. Scope and non-claims

| Question | Answer |
|---|---|
| Did the dependency qualify? | **No — BLOCKED.** |
| Did the fixture corpus qualify? | **No — BLOCKED.** |
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

**F1 (BLOCKING) — unresolved package/source version identity ambiguity.** Every version field was read
directly from the acquired artifacts:

| Object | Field | Version |
|---|---|---|
| PyPI distribution | `info.version` | `0.3.15` |
| Wheel metadata | `dist-info/METADATA` `Version:` | `0.3.15` |
| Sdist metadata | `PKG-INFO` `Version:` | `0.3.15` |
| Sdist build config | `pyproject.toml` `[project].version` | `0.3.15` |
| Rust crate | `Cargo.toml` `[package].version` | **`0.3.14`** |
| Rust lockfile | `Cargo.lock` `pyblst` entry | **`0.3.14`** |
| Compiled crate | version string embedded in `pyblst.cp312-win_amd64.pyd` | **`NOT_OBSERVABLE`** |
| Upstream tag | `OpShin/pyblst` tag `0.3.15` | `0.3.15` |
| Tag commit | `dadf9cbac859774d8e9115881b34f8e7a82e61d8` "New release with locked cargo" | — |
| Tag tree `pyproject.toml` | `[project].version` | `0.3.15` |
| Tag tree `Cargo.toml` / `Cargo.lock` | `[package].version` / lock entry | **`0.3.14`** |
| GitHub release object | — | `NONE` |

An earlier revision of this document recorded the tag as `NOT_OBSERVED`. **That was wrong and is
corrected here.** The tag exists, and so does a successful tag-triggered publish workflow:

| Fact | Value |
|---|---|
| Build workflow | `.github/workflows/CI.yml` |
| Behaviour | tag checkout → build wheels/sdist → Actions artifacts → `uv publish` (`PYPI_API_TOKEN`) |
| CI run | `18509666718`, result `SUCCESS`, head `dadf9cbac859774d8e9115881b34f8e7a82e61d8` |
| PyPI Trusted Publishing | `NO` |
| PyPI artifact attestation | `ABSENT` |

These tag facts are **controller-verified**, not re-fetched locally in this session; they are recorded as
`tag_evidence_origin: CONTROLLER_VERIFIED_NOT_LOCALLY_REFETCHED`.

A maturin project can legitimately carry a Python distribution version in `[project].version` that
differs from the Rust crate version, and the tag tree shows exactly that divergence, deliberately
committed under the message "New release with locked cargo". The divergence therefore *has* a plausible
mechanical explanation, and the tag evidence makes it materially stronger than the previous
`NOT_OBSERVED` state. It is still not sufficient, for three exact reasons:

1. **`0.3.14` is itself a separately published distribution version** of this same package (present in
   the PyPI `releases` map). The crate version inside the reviewed `0.3.15` sdist therefore names a
   *different published distribution*, rather than being an inert internal number.
2. **No artifact attestation binds the published bytes to that CI run.** Every one of the 35 files in
   the `0.3.15` release — including the exact `cp312-win_amd64` wheel and the sdist — reports
   `attestations: absent` and `provenance: null`. The workflow publishes with `uv publish` and a
   `PYPI_API_TOKEN`, not Trusted Publishing, so nothing cryptographically ties run `18509666718` to the
   exact bytes we hashed. A tag plus a green workflow proves a build *happened*; it does not prove
   *these* bytes came out of it.
3. **The compiled binary cannot be tied to the reviewed source.** The `.pyd` contains no
   `CARGO_PKG_VERSION` and no `0.3.1x` string, the module exposes no `__version__`, and the build is
   not reproducible here. `binary_source_correspondence_proven = false`.

`SOURCE_TO_SDIST_BINDING: NOT_PROVEN` and `SOURCE_TO_WHEEL_BINDING: NOT_PROVEN`.

Under the decision rules this remains case **B — an unresolved package/source identity ambiguity**, not
case A. It is recorded as `PACKAGE_SOURCE_CONTRADICTIONS: UNRESOLVED_PACKAGE_VERSION_IDENTITY_AMBIGUITY`
and it blocks `DEPENDENCY_QUALIFICATION`. It is explicitly **not** downgraded to a P3 note, and the tag
evidence was **not** inflated into attestation in order to clear the blocker.

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

**F7 (repaired) — the harness accepted an arbitrary temporal profile.** Before this revision,
`qualify_quicknet_round` honoured caller-supplied `genesis_time` and `period`, so the official round-42
signature could return `ROUND_STRUCTURALLY_VERIFIED` with `genesis_time=0`, `period=-7` and a nonsensical
`round_time` of `-287`. A successful result is a statement about the Quicknet chain, so it may only ever
be produced under the exact profile. Both parameters are now rejected unless they equal
`1692803367` / `3`, returning `CHAIN_PROFILE_BINDING_INVALID` with empty details **before** the candidate
dependency is imported and before any curve operation runs. The official defaults still yield
`round_time = 1692803490`.

**F8 (repaired) — candidate dependency exceptions escaped raw.** Point re-compression, the `bytes()`
conversion of a dependency-returned value, a non-`ImportError` raised during `import pyblst`, and a
non-`PackageNotFoundError` raised by `importlib.metadata.version` all propagated the raw exception. All
eleven dependency-controlled surfaces are now wrapped and map to `DEPENDENCY_EXCEPTION` with empty
details; `str(error)` — itself dependency-controlled — is guarded too. Intentional mappings
(`DEPENDENCY_PROFILE_UNAVAILABLE`, `DEPENDENCY_VERSION_MISMATCH`, `SUBGROUP_CHECK_FAILED`,
`*_POINT_INVALID`) are preserved. `BaseException`, `KeyboardInterrupt` and `SystemExit` are never caught,
and a permanent AST test enforces that.

**F9 (repaired) — `0x40` was classified as canonical compressed infinity.** It is not: the compression
bit `0x80` is absent, so `0x40 || zeros` is the canonical *uncompressed* infinity encoding. Canonical
*compressed* infinity requires the first byte to be exactly `0xC0`. The predicate now demands exactly
that, and the permanent test that previously pinned the wrong behaviour has been corrected. An
uncompressed-flagged input still fails closed through the ordinary point-decoding path — it is simply no
longer mislabelled as an infinity rejection.

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
| Temporal genesis override | caller genesis accepted | `CHAIN_PROFILE_BINDING_INVALID` no longer returned |
| Temporal period override | caller period accepted | `CHAIN_PROFILE_BINDING_INVALID` no longer returned |
| Dependency compress escape | re-compression wrapper removed | raw `RuntimeError` escapes |
| Dependency import escape | non-`ImportError` unwrapped | raw `RuntimeError` escapes |
| Dependency metadata escape | non-`PackageNotFoundError` unwrapped | raw `RuntimeError` escapes |
| Infinity flag widening | `0x40` counted as canonical compressed | predicate test fails |
| Provenance without pin | source hash/URI removed from a fixture | evidence test fails |
| Tag regression | `tag_version` reverted to `NOT_OBSERVED` | tag-evidence test fails |
| Dependency decision flip | `DEPENDENCY_QUALIFICATION` set to PASS | decision tests fail |
| Fixture decision flip | `FIXTURE_QUALIFICATION` set to PASS | decision tests fail |

The `hash_to_group` order trap (F5) is itself the result of the DST/message track: the initial
positive case failed with `SIGNATURE_VERIFICATION_FAILED` until the true argument order was
established, which is how the finding surfaced.

---

## 6. Fixture corpus — `FX-DRAND-QUICKNET-RFC9380-QUALIFICATION.v1`

Recorded in `tests/crypto_core/fixtures/drand_quicknet_rfc9380_qualification_v1.json`: 3 positive,
24 negative, 0 blocked. Every fixture declares its provenance; the permanent test rejects any
provenance outside the admissible set.

Positive fixtures come from the official drand HTTP API v2, pinned by URL and by the sha256 of the
raw response body:

- chain info — `ff9887bdaa43734aa86582837ef43ba1ee1b14d3bd841d5535f94651b85ab7d3`
- round 42 — `b7f86008c4b7ddffe6b8cf65371c801973360f4b13f107a9c3bf1460a6b1f44e`

### 6.1 Mandatory coverage classes — all three now provenance-backed

The previous revision recorded `blocked_subgroup_invalid_g1_point` and
`blocked_non_canonical_encoding_point` as blocked. Re-auditing the actual observed behaviour against
the decision rules shows both classes **are** satisfiable with admissible provenance, and neither
required inventing bytes. Both blocked entries are removed and replaced by real fixtures.

| Class | Fixture | Provenance | Observed blst result |
|---|---|---|---|
| subgroup-invalid | `neg_one_bit_signature_corruption` | deterministic mutation of an admitted positive | `BLST_POINT_NOT_IN_GROUP` |
| non-canonical | `neg_non_canonical_unreduced_x_signature` | pinned upstream source (below) | `BLST_BAD_ENCODING` |
| infinity | `neg_g1_infinity_signature`, `neg_g2_infinity_public_key` | pinned upstream source (below) | accepted by `uncompress`; consumer must reject |

**Provenance is a pinned source, not a label.** An earlier revision asserted
`NORMATIVE_FIELD_MODULUS_ENCODING` / `NORMATIVE_CANONICAL_ENCODING` with nothing behind them but the
string itself and a curve constant duplicated inside the test. That is circular and has been replaced
with an immutable, hash-verifiable source:

| Evidence | Value |
|---|---|
| Module | `github.com/kilic/bls12-381` `v0.1.0` (inside the official drand v2.1.6 dependency graph) |
| `go.sum` | `h1:encrdjqKMEvabVQ7qYOKu1OvhqpK4s47wDYtNiPtlp4=` |
| Source URI | `https://proxy.golang.org/github.com/kilic/bls12-381/@v/v0.1.0.zip` |
| `bls12_381.go` | `19dad068bf44c42af69fd15896540749172ec3ff31ece151c6f9d6bc3c673246` — defines `p` |
| `g1.go` | `51143a23a7818f0347b60ed6d0bdc42fbbc1640344013ffded1dd48f99a709b6` — defines the encodings |
| Licence | Apache-2.0, `58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd` |

Verbatim load-bearing lines from that pinned source:

- modulus — `// p = 0x1a0111ea397fe69a4b1ba7b6434bacd764774b84f38512bf6730d2a0f6b0f6241eabfffeb153ffffb9feffffffffaaab`
- canonicality — `return nil, errors.New("must be less than modulus")` (so canonical requires `x < p`)
- compression flag — `if in[0]&(1<<7) == 0 {` → "compression flag must be set"
- compressed infinity — `if (i == 0 && v != 0xc0) || (i != 0 && v != 0x00) {`

The permanent tests re-derive both `p` and the `0xC0` flag byte **by parsing those recorded source
lines**, then check the fixture bytes against the parsed values — so the assertion no longer depends on
the locally duplicated constant. The local constant is cross-checked only afterwards, and is not the
authority.

**Scope limit, stated plainly:** `kilic/bls12-381` is a hash-pinned upstream *implementation*, not the
normative specification. It cites the zcash BLS12-381 serialization rules as its own authority. The
manifest records `is_normative_specification: false` and every coverage entry carries
`evidence_basis: PINNED_UPSTREAM_SOURCE_NOT_NORMATIVE_SPECIFICATION`. A future admission step that needs
specification-level provenance must still fetch the specification itself.

**Subgroup-invalid.** Flipping the final bit of the official round-42 signature is a deterministic
mutation of an admitted positive fixture, which the decision rules accept as provenance. Executed
against the candidate dependency it returns `BLST_POINT_NOT_IN_GROUP` — reproduced on two runs. This is
a genuine subgroup rejection: the input is a full 48 bytes, so it is not a length rejection; it is not
infinity; and it is not a bad-encoding rejection.

**Non-canonical.** The x-coordinate is set to the BLS12-381 base field modulus `p` with the compression
bit set. `p` is a normative curve constant, and a compressed encoding is canonical only when `x < p`,
so `x == p` is non-canonical by definition. These bytes are derived from a published constant, not
fabricated. Executed against the candidate dependency it returns `BLST_BAD_ENCODING` — reproduced on
two runs.

Note precisely what this proves: blst rejects the unreduced encoding at `uncompress`, which the harness
maps to `signature_point_invalid`. The harness's own `non_canonical_encoding` reason — the
re-compression equality check — is therefore **defence in depth and unreachable for this input class**.
The coverage claim is that the non-canonical encoding is rejected, not that the harness's dedicated
non-canonical reason code fires.

**Infinity.** Canonical compressed infinity is *accepted* by `uncompress` and re-compresses to the
identical bytes, so it is neither a length nor a decode rejection. The consumer must reject it, and the
harness does, before any pairing work. Infinity coverage is therefore distinct from subgroup-invalid
coverage and is not counted as such.

### 6.2 Why `FIXTURE_QUALIFICATION` is still BLOCKED

Coverage is no longer the blocker; **licensing is**. The rules require that *every committed raw
fixture has explicit reuse/license support*. The committed official bytes (the round-42 signature, the
chain public key) are labelled `OFFICIAL_PUBLIC_RANDOMNESS_BEACON_OUTPUT` — but that is a
characterisation written here, not an explicit licence or reuse grant proven from a primary source. No
terms-of-use or licence statement for the drand beacon data was ever fetched or verified.

Recorded honestly as `license_explicitly_proven: false` on each official positive fixture, and as
`FIXTURE_QUALIFICATION: BLOCKED` with blocker `fixture_license_unresolved`. Resolving it needs a
primary-source licence/reuse statement for drand beacon output, which is an external-fact question for
controller-orchestrated Deep Research — not something to settle by assertion here.

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
- **Windows/CPython 3.12 only.** The wheel examined here is `cp312-win_amd64`. No claim is made for
  any other platform, architecture or Python version.
- **F1 is unresolved and blocking**, not waived and not a P3 note.
- **Fixture licensing is unresolved**, not assumed.

---

## 8. Decision

```
DEPENDENCY_QUALIFICATION:      BLOCKED
DEPENDENCY_BLOCKERS:           package_version_identity_ambiguous
FIXTURE_QUALIFICATION:         BLOCKED
FIXTURE_BLOCKERS:              fixture_license_unresolved
PACKAGE_SOURCE_CONTRADICTIONS: UNRESOLVED_PACKAGE_VERSION_IDENTITY_AMBIGUITY
```

`DEPENDENCY_QUALIFICATION` cannot be `PASS_CANDIDATE_ONLY`. That result requires, among other things,
that there be *no unresolved package/version identity ambiguity*. F1 is exactly such an ambiguity: the
Rust crate version inside the reviewed sdist names a different published distribution, the upstream tag
and its successful publish workflow exist but carry no Trusted Publishing or artifact attestation
binding the exact PyPI bytes to that run, and the compiled binary cannot be tied to the reviewed source
tree. Case B applies, so the decision is BLOCKED. The blocker wording is refined to name the missing
artifact binding rather than a missing tag — but it is not removed by inference.

`FIXTURE_QUALIFICATION` cannot be `PASS_CANDIDATE_ONLY` either. All three mandatory coverage classes —
subgroup-invalid, non-canonical and infinity — are now provenance-backed (§6.1), which closes the
previous coverage blockers. But explicit reuse/licence support for the committed official beacon bytes
was never proven from a primary source (§6.2), so the decision is BLOCKED on
`fixture_license_unresolved`.

Permanently, and independently of the above:

```
DEPENDENCY_ADMITTED:              NO
FIXTURE_CORPUS_ADMITTED:          NO
CRYPTO_IMPLEMENTATION_AUTHORIZED: NO
PROVIDER_OPERATIONAL_APPROVAL:    NO
MT4_VERIFIER_PROFILE_SELECTED:    NO
READINESS_PROMOTED:               NO
MACHINE_TIME_ORIGIN_PROVEN:       NO
TIMESTAMP_ORIGIN_PROVEN:          NO
PROOF_VERIFIED:                   NO
OPERATIONAL_USE_APPROVED:         NO
QUORUM_COUNTABLE:                 NO
OPERATIONAL_QUORUM_READY:         NO
```

What survives as useful candidate evidence: the exact chain profile (§2), the exact artifact hashes
(§3), the official reference agreement (§4), the ten causal tracks (§5), the fixture corpus (§6), and —
most importantly — the F5 argument-order trap, which any future verifier must respect regardless of
which dependency is eventually admitted.

To move either decision off BLOCKED, two external-fact questions must be answered by
controller-orchestrated Deep Research:

1. Can the exact PyPI wheel/sdist bytes be bound to tag commit `dadf9cba` — e.g. by recovering the
   artifact hashes from CI run `18509666718`, by a reproducible build, or by a maintainer statement?
   The tag and the green workflow are already established; what is missing is the artifact binding.
2. What explicit licence or reuse grant covers drand Quicknet beacon output committed as test fixtures?

**Next safe action:** none in this slice. MT4-S3B (verifier profile selection) must not begin, and no
production BLS verification code may be written, until both decisions are resolved under separate
authorization and an independent Class-C audit.
