# Machine-Time Provenance (MT) — Design Contract (Fable-authored, 2026-07-08)

Status: DESIGN ONLY. Purpose: upgrade operator-attested operational days
(`operator_attested_not_machine_proven.v1`, #318/#319) to MACHINE-PROVEN days — the only path by
which `machine_time_origin_proven` may ever become True, and one of the two hard prerequisites of
completion v3. Injected deterministic time is never wall-clock proof; attestation is never machine
proof (§21.5) — MT exists to replace both with external cryptographic evidence.

## 1. The sandwich model (core idea)

A day's evidence is provably inside a real-time interval when it is sandwiched between two
independent external time proofs:

- **Not-before**: a public randomness/time beacon value (unpredictable before publication) is
  embedded INTO the attested-day metadata at seal time. The day's digest therefore cannot have
  been created before the beacon value existed.
- **Not-after**: a signed timestamp from an external authority COMMITS TO the day's self-digest.
  The digest therefore existed no later than the signed time.
- **Quorum**: >= 2 independent source CLASSES on each side (e.g. randomness beacon + timestamping
  authority; concrete registry is post-DR). Single-source compromise must not forge time.
- **Spacing**: 30 machine-proven days require 30 distinct sandwiches whose not-before/not-after
  intervals are consistent with ~30 real elapsed days — compressing a month of evidence into one
  afternoon becomes cryptographically impossible, not just policy-forbidden.

## 2. Artifact sequence (MT-2..MT-6; MT-2 is pre-DR-safe, MT-3+ need DR facts)

1. **MT-2 `machine_time_policy.py` — `MachineTimePolicy`** (ABSTRACT, pre-DR-safe): pins the
   sandwich structure — required roles (not_before, not_after), quorum >= 2 independent classes
   per role, verification-policy identifiers as abstract strings, spacing rules, canonical
   encoding of proofs. NO concrete provider names/endpoints (those are DR-gated).
2. **MT-3 `machine_time_source_registry.py`** (POST-DR): concrete source classes with verification
   parameters compiled from the Deep Research round (beacon format, signature scheme, RFC 3161 TSA
   semantics, roughtime behavior, exchange-time reliability — all facts cited, none from memory).
   Every registry entry carries the DR citation id; unverifiable facts stay out.
3. **MT-4 `machine_time_anchor_evidence.py`**: one verified sandwich for one digest — carries raw
   proof bytes (canonically encoded), verification result per source, quorum satisfaction; verify
   is deterministic re-check of supplied proofs (no network at build time — proofs are inputs).
4. **MT-5 `machine_proven_operational_day_evidence.py`**: joins an attested day (#318) with its
   MT-4 anchors; the ONLY artifact that may set `machine_time_origin_proven=True`, and only when
   both roles + quorum + digest-commitment checks pass.
5. **MT-6 `machine_proven_thirty_day_gate_decision.py`**: >= 30 consecutive machine-proven UTC
   days, same market/correlation discipline as #319, PLUS interval-consistency across days
   (spacing rule). Output feeds completion v3.

## 3. Cross-cutting invariants

- Proof bytes are INPUTS; builders verify deterministically and never fetch. Any network fetch
  belongs to an explicitly authorized, separate operational step that only PRODUCES input files.
- Digest commitment is exact: not-after proofs must commit to the day self-digest (or its
  canonical hash chain), never to a truncation or re-encoding.
- Clock-skew tolerances, revocation handling, and proof-format versions are GOVERNANCE_REQUIRED
  after DR; the policy structure carries the fields, humans approve the values.
- Non-overclaim: MT proves TIME EXISTENCE of evidence, never operational quality, edge,
  profitability, readiness, or completion. All unrelated flags stay structurally False.

## 4. Deep Research batch (runs combined with the funding pilot round, PRM-07+16)

Questions: current beacon options and their publication cadence/signature verification; RFC 3161
TSA availability and verification semantics; roughtime ecosystem status; exchange server-time
trustworthiness (likely NOT quorum-eligible alone); recommended proof archival formats. Output
becomes MT-3 registry constants with citations; anything unverifiable stays `UNPROVEN` and out of
the registry.

## 5. Test-matrix skeleton

Happy sandwich; missing role; quorum=1; digest-commitment mismatch (tampered day); beacon value
reused across days (replay); interval inconsistency (30 days sealed in 1); proof-format tamper;
structural-False AST; determinism (same proofs → same digest).

## 6. Stop conditions

Any concrete provider fact without a DR citation; any temptation to let injected/attested time
satisfy an MT check; any network call inside a builder; scope beyond the named slice.
