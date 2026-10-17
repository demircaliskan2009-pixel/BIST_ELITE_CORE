# C platform binary/loader qualification v1

This is an offline, non-production qualification implementation. Nothing here
admits a source, native artifact, trust root, verifier, provider or machine-time
proof. All build/test receipts are `CANDIDATE_TEST_EVIDENCE_ONLY`; synthetic
signed vectors are `SYNTHETIC_TEST_ONLY`. Existing B artifacts, blst profile
commitments and trusted attestation workflows are untouched.

The implementation was requested under
`PROJECT_INSTRUCTION_DRIFT=TEMPORARY_SOL_IMPLEMENTATION_REQUEST`. This records a
temporary human exception, not an accepted amendment to section 24. No execution
on the implementing model id is eligible to independently audit this candidate.
Self-checks satisfy no protected audit or merge gate.

## Boundary and prerequisites

`c_build_candidates.py` checks the previously authenticated OpenSSL 3.5.9 archive
digest and the existing blst v0.3.17 commit/tree identity. It exports immutable
git objects rather than executing blst checkout bytes, and records commands,
compiler output and exact binary digests. Rebuilding never inherits admission
from a recipe or an old binary. The local operator/runner provisions the tools;
the builder installs no tools or dependencies. Python 3.12 is required for the
qualification builder's safe tar extraction, independent of the product floor.

OpenSSL is linked statically into a narrow C shim and built without shared
modules, DSO loading or engines. It does not load OpenSSL configuration or default
trust stores. The OS runtime is a separate dependency boundary; a static
libcrypto link does not make the resulting image fully static.

`c_native_formats.py` bounds and inspects x64 ELF/PE images before mapping,
requires exports and rejects unsupported architecture/ABI, writable executable
segments, ELF loader search/audit paths, PE delay/bound imports and forwarded
candidate exports. This is an intentionally strict build profile, not a general
ELF/PE validator or a source authentication mechanism.

`c_native_loader.py` hashes immutable supplied bytes, inspects them and derives
the platform from the host. Windows staging uses an explicit owner-only DACL,
CREATE_NEW, directory read handles that deny delete sharing for every ancestor,
and a read-only target handle that denies write/delete sharing.
The file DACL permits reads/execution, denies later writes and removes the owner's implicit WRITE_DAC
through OWNER RIGHTS, including the interval between creator close and guard
reopen. File identity and
content are re-proven after closing the creator handle, before loading, and after
loading. DLL search is restricted to System32. The loaded module path must equal
the protected private path. Linux uses a memfd with WRITE/GROW/SHRINK/SEAL seals,
loads its held descriptor and re-proves mapped device/inode identity. Protection
is held until unload. Callables are not returned to callers after closing.

Only the bounded platform OS library baseline is supported; third-party shared
dependencies are rejected. Linux requires unprivileged execution, no active
LD_* settings or system preload file, and uniquely mapped root-owned immutable
OS dependencies. Windows rejects preloaded direct dependencies outside System32.
Observed OS file hashes are recorded and checked again after mapping.

**Dependency limit:** this does not independently authenticate an OS installation
or qualify its full transitive/API-set/forwarder closure. The OS loader and its
trusted system runtime remain a platform assumption. Qualification/admission
must remain blocked if the required OS-baseline provenance or transitive
dependency evidence is absent. These mechanisms must not be connected to a
product verifier as if that missing evidence had been supplied.

## RFC3161 qualification profile

The C shim requires exact OpenSSL 3.5.9 and a versioned x64 C ABI. It verifies
SHA256 messageImprint, nonce, explicit numerical policy OID, token signature,
exact signer-certificate SHA256, explicit root and embedded intermediate chain,
timestamp EKU, ESSCertID/ESSCertIDv2 via OpenSSL's timestamp signature verifier,
genTime, authenticated accuracy and certificate validity at genTime. Verification
time and maximum accuracy are supplied inputs. Unknown response/request
extensions, absent accuracy and unsupported time encodings fail closed.

`TS_REQ_to_TS_VERIFY_CTX` omits `TS_VFY_SIGNATURE`. The shim explicitly adds the
complete immutable required flag set, including signature verification, and
rejects a different asserted flag set. No caller can select a signature-disabled
path. [OpenSSL context API](https://docs.openssl.org/3.5/man3/TS_VERIFY_CTX/)
and the authenticated release's `crypto/ts/ts_verify_ctx.c` define that boundary.

Revocation uses supplied full direct CRLs for every non-anchor certificate.
Issuer signatures, CRL-sign key usage, explicit as-of freshness and issuer
validity at CRL issuance are checked. A listed serial is conservatively rejected,
including post-genTime revocations. Ambiguous issuer CRLs, scoped/indirect/delta
CRLs, critical CRL extensions and OCSP-only evidence are rejected. This strict
qualification profile creates no operational revocation policy or trust authority.

The vector generator runs inside the protected source-built qualification DLL to
create disposable synthetic roots, real signatures and CRLs. It uses fixed test
instants and nonce, with no wall-clock input. Keys never leave native memory;
byte reproducibility of randomly generated test keys is not claimed. Native tests verify repeatability on the
same proof bytes and negative signature/signer/policy/imprint/nonce/time/accuracy/
CRL cases. Missing native material is BLOCKED locally and fails required-native
CI mode. An unexecuted native test is not a pass.

## Execution and evidence

From the repo root in a provisioned unprivileged environment:

```text
python -m scripts.crypto_core.qualification.c_build_candidates --openssl-archive <authenticated-archive> --blst-checkout <clean-pinned-checkout> --output <fresh-build-directory>
python -m scripts.crypto_core.qualification.c_rfc3161_vectors --receipt <build-directory>/build-receipt.json --output <fresh-synthetic-vector-directory>
```

Set `C_NATIVE_BUILD_RECEIPT` and `C_RFC3161_VECTORS` to the resulting JSON files.
Set `C_REQUIRE_NATIVE=1` when native qualification is mandatory. Execute the two
`test_c_native_*.py` files through `run_logged_command.ps1`; use
`c_qualification_matrix.py` to turn their actual JUnit XML into the required
per-test command/platform/expectation/result/status/evidence rows. Run the full
suite through `run_full_tests_logged.ps1` after the final mutation. Only its
`PYTEST_EXIT=0` proves that local full-suite gate.

The new qualification-only workflow uses read-only repository permission,
exact-head checkout, pinned actions and separate Windows/Linux runners. It
requests no OIDC, signing, attestations, secrets or operational admission. A
workflow definition or green job never proves an unexecuted platform test.

`c_pynacl_inventory.py` observes the existing PyNaCl 1.6.2/cffi installation,
checks RECORD consistency and hashes native files without importing them. RECORD
is not authenticated wheel provenance; bundled libsodium build identity remains
unproven until exact wheel/source/build evidence is supplied. No production
dependency manifest is changed.

## Gate identities retained

DEP-G1 is authenticated OpenSSL source; DEP-G2/G3 are independently qualified
Linux/Windows OpenSSL binaries; DEP-G4 is full RFC3161 qualification; DEP-G5 is
the governed blst native-loader boundary; DEP-G6 is complete cross-platform
native/adversarial evidence; DEP-X1 is the PyNaCl/cffi/libsodium chain if reused.
Each remains open until its own evidence exists. Missing ESS/EKU/chain/historical
negative vectors, complete dependency provenance and end-to-end race tests must
be reported explicitly rather than inferred from header or plain-file tests.
MT-4/5/6, source admission, real proofs, Stage-4, live/capital and merge authority
are outside this implementation.
