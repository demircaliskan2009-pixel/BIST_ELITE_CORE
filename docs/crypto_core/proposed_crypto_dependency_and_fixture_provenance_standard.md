STATUS: PROPOSED_DRAFT_NOT_CURRENT_AUTHORITY

This document is a non-authoritative proposal. It is not an admission policy,
not current governance authority, not Class-C approved, not human approved, and
not permission to alter an existing dependency, fixture, identifier, readiness,
connector or MT4 decision.

---

# Proposed crypto dependency and fixture provenance criteria (DRAFT)

## 0. What this document is, and what it is not

This draft records the unresolved cryptographic dependency and fixture provenance policy questions
surfaced by the MT4-S3A qualification attempt. Every requirement below is marked `PROPOSED` and none
of them is in force.

| Question | Answer |
|---|---|
| Does this document admit a dependency? | No. |
| Does this document admit a fixture corpus? | No. |
| Does this document bind `D-DEP-02` or `FX-DRAND-QUICKNET.v1`? | No. |
| Does this document decide identifier interpretation A or B? | No. That is a separate decision. |
| Does this document authorize MT4-S3B or verifier-profile selection? | No. |
| Does this document change readiness or connector state? | No. |
| Does this document change any MT4-S3A decision or blocker? | No. |
| Is this document Class-C audited? | No. |
| Is this document human-approved governance? | No. |
| Does it add or change any executable invariant? | No. It adds no test and no runtime code. |

The mandatory independent Class-C audit of MT4-S3A is `DEFERRED_NOT_WAIVED`. Nothing here substitutes
for it, and the absence of that audit is not evidence of anything.

### 0.1 Source pins used by this draft

The records below are pinned and selectively restated for context. Their source artifacts remain
authoritative. If a restated value conflicts with its pinned source, the source controls and this
draft is stale. Pinning fixes what a citation refers to; it does not make surrounding prose incapable
of drifting from it.

| Record | Pin |
|---|---|
| MT4-S3A qualification packet | branch `wip/crypto-core-mt4-s3a-drand-quicknet-qualification` @ `5678b618d28488c7624e0e3adb9853d9b1dfbfb9` |
| — qualification document | `docs/crypto_core/mt4_s3a_drand_quicknet_pyblst_qualification.md`, blob `9b054f49f80b2c7aebc96d1eb0bbbba2bd471d67` |
| — qualification harness | `scripts/crypto_core/qualify_drand_quicknet_pyblst.py`, blob `ebcf58120053a06a6a160465f195e7edfdabe46d` |
| — fixture manifest | `tests/crypto_core/fixtures/drand_quicknet_rfc9380_qualification_v1.json`, blob `787b79f465ee6b2ff28d2cc4f7a1975cdb385590` |
| — permanent tests | `tests/crypto_core/validation/test_drand_quicknet_rfc9380_qualification_manifest.py`, blob `9917bfbd86017e6c1f8cfdc930827300c8c6924c` |
| This draft's base | `origin/main` @ `15e9366ed2bca3d8cf84a945aba721e3546d9355` |

Note on reachability: `machine_time_source_trust_snapshot.py` and
`machine_time_drand_quicknet_chain_profile.py` are **not present on `main`** at this draft's base. Where
this draft cites them, it cites them at the MT4-S3A frozen head above, which contains them.

---

## 1. Current external decisions — cited, not modified

These values are the property of their own artifacts. This draft reproduces them for context only and
changes none of them. If any value below ever disagrees with its source artifact, the source artifact
is correct and this draft is stale.

```
DEPENDENCY_QUALIFICATION:      BLOCKED
DEPENDENCY_BLOCKERS:           package_version_identity_ambiguous
FIXTURE_QUALIFICATION:         BLOCKED
FIXTURE_BLOCKERS:              fixture_license_unresolved
                               mandatory_subgroup_invalid_fixture_provenance_unresolved
SOURCE_TO_SDIST_BINDING:       NOT_PROVEN
SOURCE_TO_WHEEL_BINDING:       NOT_PROVEN
FIXTURE_REUSE_LICENSE:         NOT_PROVEN
FIXTURE_REUSE_SCOPE:           UNKNOWN
ATTRIBUTION_REQUIRED:          UNKNOWN
DEPENDENCY_ADMITTED:           false
FIXTURE_CORPUS_ADMITTED:       false
MT4_S3B_AUTHORIZED:            false
READINESS_PROMOTED:            false
```

Authoritative sources: the `admission` block of the fixture manifest, and the module-level decision
constants in the qualification harness, both at the frozen head pinned in §0.1.

`NOT_PROVEN` means the evidence available did not establish the claim. It is not `DISPROVEN` and not
`IMPOSSIBLE`. `UNKNOWN` means the value or scope has not been established at all. Neither may be read
as a negative finding, and neither may be converted into a pass.

---

## 2. Identifier contract

```
IDENTIFIER_SEMANTICS:            UNKNOWN
SAFE_IDENTIFIER_CLASSIFICATION:  OPAQUE_PINNED_IDENTIFIERS_WITH_UNDEFINED_MAPPING
AFFECTED_IDENTIFIERS:            D-DEP-02, FX-DRAND-QUICKNET.v1
IDENTIFIER_REBIND_RULE:          NO_REBIND_WITHOUT_EXPLICIT_CONTROLLER_APPROVED_IDENTIFIER_MAPPING
```

### 2.1 What is established

- `D-DEP-02` is pinned as `dependency_profile_id`, and `FX-DRAND-QUICKNET.v1` as `fixture_corpus_id`,
  inside the whole-row eligibility tuple at
  `src/crypto_core/validation/machine_time_source_trust_snapshot.py:105-106` (MT4-S3A frozen head).
- The same two values are pinned again at
  `src/crypto_core/validation/machine_time_drand_quicknet_chain_profile.py:90-91` and mirrored into
  that artifact's bound row and self-digested descriptor.
- A repository-wide search finds both strings only in those two modules and their two test modules.
- **No authoritative repository mapping currently defines which exact admitted artifact either
  identifier denotes.**

### 2.2 What is not established

The absence of a mapping definition establishes nothing about the identifiers' semantics. It is
absence of evidence, not evidence that either identifier may be pointed at a different artifact.
Their meaning is `UNKNOWN`.

### 2.3 Two possible future interpretations (PROPOSED — this draft does not choose)

- **Interpretation A** — the identifier is an explicitly versioned logical identifier whose
  replacement semantics are defined, bounded and enforced by permanent tests.
- **Interpretation B** — the identifier denotes one exact dependency or corpus identity, so a
  different dependency or corpus requires a new identifier and a reissue of the artifacts that pin
  the old one.

`PROPOSED` default: **B**, until A is proven and explicitly approved. The choice between A and B is a
separate controller and human governance decision and is deliberately not made here.

### 2.4 Consequences to cost under the default (PROPOSED)

Under default B, admitting any dependency or corpus whose identity differs from whatever these
identifiers denote requires reissuing the artifacts that pin them. Both identifiers sit inside the
digested descriptors of both artifacts, so a reissue changes the trust-snapshot self-digest and the
chain-profile self-digest, and the digests carried downstream from them. Digests computed over the
MT-3 registry record and over chain-info do not carry either identifier and are not affected.

Because both identifiers live in the same row and the same descriptor, a coordinated dependency and
corpus selection can be absorbed by a single reissue. That is a sequencing observation, not an
authorization to perform one.

### 2.5 Prohibited characterisations

Neither identifier may be described as a slot, as rebindable, as replaceable, as an alias, or as an
abstract admission target. Under B, retaining the current candidate would equally require an explicit
mapping decision — the default privileges no candidate, including the incumbent.

---

## 3. PROPOSED dependency evidence taxonomy

Each class below is distinct evidence. No class may stand in for another, and a strong value in one
class never satisfies a requirement in another.

| Class | PROVES | DOES NOT PROVE |
|---|---|---|
| Signed source authenticity | a specific commit object is authentic and untampered | anything about any published artifact |
| Source-tree identity | the exact file content at a commit | that a build used that tree |
| CI-run identity | a run existed and was triggered at a stated head | which bytes it emitted, or where they went |
| CI workflow success | a build completed without a non-zero exit | that published bytes came from it |
| Archive-container digest | the digest of a container (e.g. a ZIP) | the hash of any individual file inside it; container digests move with compression, timestamps and metadata even when the payload is identical |
| Individual artifact file hash | the exact bytes of one wheel or sdist file | which build produced it |
| Published artifact hash | the exact bytes an index serves | provenance of those bytes |
| Generic artifact attestation | after signature verification and issuer-identity verification, that an authenticated issuer made the claims encoded in the exact attestation predicate about an exact subject digest | build provenance, source correspondence, builder identity, correctness, licence or maintenance quality — none of these unless that property is explicitly carried by the predicate and accepted under a verification policy |
| Verified build-provenance attestation | only the build and source correspondence explicitly established by the verified predicate, together with the subject digest, the issuer identity, the builder identity, the source reference and the verification policy under which it was accepted | cryptographic correctness, licence sufficiency, runtime safety, maintenance quality or vulnerability-response quality |
| Source-to-artifact correspondence | published bytes were produced from a stated source | that the compiled contents match that source |
| Binary-source correspondence | a compiled object corresponds to a stated source tree | source authenticity by itself |
| Maintainer testimony | a human assertion, attributable and reviewable | a cryptographic binding; unsupported testimony is not attestation |
| Reproducible-build proof | independent parties derive byte-identical output from a pinned source and toolchain | that the original publisher used that toolchain, unless the output matches the published bytes exactly |
| Controlled project build | exactly what this project built, from what pinned inputs | anything about a third-party published artifact |
| Runtime behavioural agreement | outputs agree with a reference implementation on compared cases | provenance of any artifact |

On attestations specifically: an attestation is a signed statement, and what it is worth depends
entirely on its predicate, its subject digest, the issuer identity that signed it, the builder
identity it names, and the verification policy under which a consumer accepts it. No named
attestation format or publishing mechanism — including Trusted Publishing, PEP 740 or any successor —
automatically satisfies a provenance requirement. The actual predicate and the actual identities must
be inspected each time, and a format name is never a substitute for that inspection.

The classes above stay distinct and none of them collapses into another: an artifact hash names bytes;
an attestation is a signed claim about a subject digest; source-to-artifact correspondence is the
claim that published bytes came from a stated source; binary-source correspondence is the claim that a
compiled object matches a stated source tree; and a reproducible-build proof is an independently
re-derived byte-identical result. Establishing one of these never establishes another.

### 3.1 Hard prohibitions (PROPOSED)

- A signed source commit does not bind a wheel or an sdist.
- A green workflow does not bind published bytes.
- An archive or container digest is not an individual wheel or sdist hash and may not be compared
  against one.
- Behavioural agreement is not artifact provenance.
- A project-controlled rebuild creates a new profile; it becomes evidence about an existing published
  artifact only if exact byte correspondence with that artifact is independently proven.

### 3.2 PROPOSED conservative candidate criteria

Offered as criteria a future candidate could be measured against. They are not in force, they admit
nothing, and they select or recommend no candidate.

Cryptographic capability: BLS12-381; the orientation the target chain uses; RFC 9380 hash-to-curve
with a caller-supplied domain separation tag; subgroup checks on decode; a decode path that lets the
consumer reject the point at infinity explicitly; canonical-encoding enforcement.

Interface safety: a documented and upstream-tested argument contract for hash-to-curve. MT4-S3A
recorded a case where parameter names were the reverse of the true positional order and the wrong
order produced a different, self-consistent point that never verified, without raising. Any candidate
must have this proven rather than assumed.

Fail-closed integration: deterministic API; bounded diagnostics that never echo caller bytes; no
hidden network access; no runtime artifact acquisition.

Governance: an explicit machine-declared licence with SPDX metadata; more than one maintainer or an
institutional owner; a stated vulnerability-response path; a stated platform and interpreter matrix;
and source-to-artifact provenance available by construction rather than by later investigation.

Integration pattern: auditability at the Python/native boundary consistent with the pattern already
merged in this repository (§7).

### 3.3 Identification of candidates

Identifying actual candidate packages requires current external facts and is out of scope here. See
the Deep Research packet in §9. No alternative candidate dependency is selected, recommended,
qualified or admitted in this draft. References to the existing `PyNaCl` and `pyblst` records are
contextual evidence only, and no external package is newly proposed here.

---

## 4. PROPOSED fixture rights and provenance taxonomy

These are ten distinct things. Establishing one establishes none of the others.

| Class | Meaning |
|---|---|
| Software licence | terms governing program code |
| Documentation licence | terms governing prose and specifications |
| API access | permission or ability to call an endpoint |
| Public availability | the data can be retrieved by anyone |
| Public verifiability | the data can be checked by anyone |
| Data-copying rights | permission to copy the data itself |
| Repository-commit rights | permission to store the data in a version-controlled repository |
| Redistribution rights | permission to distribute the data onward, including forks and mirrors |
| Derivative-fixture rights | permission to produce and distribute modified or derived vectors |
| Attribution and notice obligations | what must be credited or reproduced, and where |

### 4.1 Hard prohibitions (PROPOSED)

- Public data is not automatically licensed data.
- API documentation is not a redistribution grant.
- A software or documentation licence does not automatically license API response data.
- "Public randomness", "publicly available" and "publicly verifiable" are descriptions of
  availability, not grants.
- **No unresolved legal or rights question may be converted into a technical PASS.** Where rights are
  unresolved, the correct outcome is a recorded `NOT_PROVEN` or `UNKNOWN` and a blocked decision.

### 4.2 PROPOSED shape of a sufficient grant

A grant sufficient to commit third-party response data as repository fixtures would need to be a
published primary source, attributable to a party with authority over the data, and explicit about:
copying; storage; committing to a version-controlled repository; redistribution with repository
history including forks and mirrors; use as software test fixtures; deterministic derivative vectors;
commercial and non-commercial use; and attribution or notice obligations, stated or explicitly waived.

Whether any given party holds the authority to grant such terms for data produced by a distributed
group of operators is itself `UNKNOWN` and must not be assumed.

---

## 5. PROPOSED L1–L4 fixture evidence layers

| Layer | Content | Committed to the repository? |
|---|---|---|
| L1 | licensed or rights-free deterministic protocol-conformance vectors | yes |
| L2 | hash-pinned, citation-backed chain and profile metadata, without disputed beacon response payloads where possible | yes |
| L3 | non-redistributed external interoperability observations, recorded as evidence | no — payload is not committed |
| L4 | official beacon fixtures | only after explicit rights are proven |

Claim boundaries, proposed as binding on any future implementation of this model:

- L1 proves protocol conformance. It does not prove official interoperability.
- L2 proves recorded profile identity. It does not prove that any beacon signature is valid.
- L3 is evidence. It is not an admitted committed fixture, and an L3 payload must never be silently
  promoted into one.
- Only L4 can provide repository-committed official interoperability evidence.
- No layer may inherit a stronger claim from another layer.

A future implementation of this model would need a permanent test enforcing the L3 boundary, so the
promotion prohibition is executable rather than a prose promise. This draft adds no such test.

---

## 6. PROPOSED anti-circularity rule

A derived fixture may be called provenance-backed only when its base fixture is itself admitted, and
the base's admission must be provable independently of the derivation.

A derived fixture must never be called provenance-backed merely because it was derived from an
unadmitted positive. Retaining such a fixture as candidate evidence, clearly labelled as not
provenance-backed, remains legitimate: the observation can be real and useful while the provenance
claim is withdrawn.

Direct construction from pinned, licensed mathematical source material is a **separate** provenance
path from derivation from a positive fixture, and must be classified separately rather than folded
into the derivation path.

---

## 7. Merged baseline context

Recorded factually, at this draft's base `origin/main` @ `15e9366ed2bca3d8cf84a945aba721e3546d9355`.

- `PyNaCl==1.6.2` is pinned in the project dependency files (`pyproject.toml:13`,
  `requirements.txt:9`).
- The repository contains a merged Roughtime verification pattern that delegates only the final
  cryptographic group-equation check to that pinned backend, and enforces in-repository fail-closed
  policy hardening before the backend is invoked — exact types, exact lengths, canonical encoding,
  scalar bounds and a documented small-order rejection inventory transcribed from the backend's own
  shipped source, with every backend exception normalized into a closed reason enum
  (`src/crypto_core/validation/roughtime_v19_certificate_verification.py`, see the module docstring
  and lines 105 and 129).
- **This existing baseline must not be used as an argument to lower MT4-S3A standards.** Nothing in
  this section proposes any change to `PyNaCl` or to any existing dependency.
- The repository currently lacks a general authoritative crypto dependency and fixture admission
  standard; qualification criteria have been argued per slice.

Classification of that last statement: `PROPOSED_GOVERNANCE_GAP_FINDING`.

---

## 8. Rights-scope caution and the independent Roughtime gate

### 8.1 Rights scope — `UNKNOWN`

Verified at this draft's base: the Quicknet chain public key and chain hash are present on `main` as
citation-backed provider facts inside the MT-3 registry record
(`src/crypto_core/validation/machine_time_source_registry.py:466`, `:468`, `:472`), carried as
documented facts with official citation identifiers rather than as a stored raw API response body.

Classified `UNKNOWN`: whether the beacon-output fixture redistribution and licensing question applies,
legally or contractually, to those committed chain parameters. This draft makes no claim that merged
`main` is non-compliant, proposes no change to it, and does not classify this as a defect. It is
carried only as a research and legal-scope question (§9, F4).

### 8.2 Independent Roughtime gate

Resolving the MT4-S3A dependency and fixture blockers does not by itself authorize MT4-S3B. The
following registry decisions are independent of those blockers and remain, at this draft's base
(`src/crypto_core/validation/machine_time_source_registry.py:298`, `:300`):

```
roughtime_protocol_provenance_required_before_mt4_profile_selection: true
roughtime_deployed_protocol_version_proven:                          false
```

No inference from dependency or fixture progress may clear that gate.

---

## 9. PROPOSED Deep Research request packet

No unresolved external research question in this packet is answered here. Repository facts are stated
only when pinned to exact repository refs or artifacts (§0.1). All external questions D1–D4 and F1–F4
remain open, and I1 remains a `CONTROLLER_GOVERNANCE_DECISION_REQUIRED` item rather than a research
answer.

### Dependency

- **D1** — Which currently maintained, CPython-compatible BLS12-381 dependencies support Quicknet
  G2-public-key / G1-signature verification, an exact caller-supplied domain separation tag, RFC 9380
  hash-to-curve, and fail-closed decoding?
- **D2** — For each candidate: current licence, SPDX metadata, maintainership, supported wheels and
  platforms, vulnerability process, Trusted Publishing, PEP 740 or other artifact attestations, and
  exact source-to-artifact binding.
- **D3** — Is there any primary-source evidence binding the exact `pyblst` 0.3.15 wheel and sdist
  hashes to the signed source commit recorded in the MT4-S3A packet?
- **D4** — Are byte-reproducible Windows maturin/PyO3 wheels realistic under a fully pinned toolchain,
  and exactly which inputs must be pinned to achieve it?

### Fixture

- **F1** — What explicit official rights govern copying, committing, redistributing and derivative use
  of drand beacon output as repository test fixtures?
- **F2** — Do licensed BLS12-381 G1 subgroup-invalid vectors exist whose data files are explicitly
  inside the licence scope?
- **F3** — Do official or normative serialization and hash-to-curve vectors exist with explicit reuse
  terms covering the non-canonical, infinity and subgroup cases?
- **F4** — Does legal or contractual rights treatment differ between documented chain parameters and
  beacon response output?

### Identifier

- **I1** — `CONTROLLER_GOVERNANCE_DECISION_REQUIRED`. What do `D-DEP-02` and `FX-DRAND-QUICKNET.v1`
  denote, and does interpretation A or interpretation B apply? This is a repository governance
  decision, not an external factual research question, and it gates every admission path.

---

## 10. Authority promotion path

This draft can become current authority only through a separate sequence containing all of:

1. controller audit;
2. independent Class-C audit where applicable;
3. explicit human governance approval;
4. an authorized repository workflow decision;
5. permanent executable invariants where required.

This draft satisfies none of these gates. Until all of them are satisfied, no slice may cite this
document as governing, and nothing in it may be used to admit a dependency or fixture, bind an
identifier, authorize MT4-S3B, change readiness or connector state, or alter any MT4-S3A decision.
