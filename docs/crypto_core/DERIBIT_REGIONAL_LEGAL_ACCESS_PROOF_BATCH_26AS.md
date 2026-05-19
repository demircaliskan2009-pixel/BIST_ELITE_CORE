# Deribit Regional Legal Access — Proof Batch (Phase 26AS)

status: PROOF_BATCH
phase: 26AS
reviewed_at_iso: 2026-05-19T00:00:00Z
supersedes: N/A (first proof batch for regional_legal_access)

---

## Purpose

This proof batch classifies the three pending rows related to regional and
legal access for Deribit. It is based on the Deep Research pack produced
in Phase 26AR (`DERIBIT_REGIONAL_LEGAL_ACCESS_RESEARCH_PACK_26AR.md`).

It does not approve any claim or policy row. It does not enable any
connector, runtime, or live integration. It documents the readiness
classification for each row prior to operator review.

---

## Row Classifications

| row_id | surface | classification | action_required | connector_runtime_implication |
|---|---|---|---|---|
| `regional_legal_access` | `claim_review` | `LEGAL_DOC_PROOF_READY_NOT_APPROVED` | Operator approval with scope limits and reviewer metadata | NONE |
| `regional_legal_access_review` | `policy_review` | `LEGAL_REVIEW_READY_FOR_OPERATOR_SIGNOFF` | Operator legal signoff (external, cannot be auto-approved) | NONE |
| `separate_connector_enablement` | `policy_review` | `DEFER_SEPARATE_PHASE` | Defer to dedicated PUBLIC_MARKET_DATA_ONLY connector phase | NONE |

---

## Row Detail

### `claim_review:regional_legal_access`

**Classification**: `LEGAL_DOC_PROOF_READY_NOT_APPROVED`

**Evidence basis**:
- Turkey is not listed in the Deribit restricted jurisdictions
  (`#restricted-countries`) as of the Phase 22L documentation snapshot
  (`source_sha256: a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd`).
- Unauthenticated public WebSocket API is documented and confirmed.
- No Turkey-specific affirmative legal clearance exists.
- Market data is personal-use-only without prior written Deribit approval.

**Approval scope if approved**:
`Phase26AR_TURKEY_PUBLIC_MARKET_DATA_ONLY_NO_LOGIN_NO_PRIVATE_API_NO_ORDERS_NO_LIVE`

**Approval gate**: Operator metadata review only — no external legal counsel
required for the claim row itself. The policy row (`regional_legal_access_review`)
is the legal-signoff gate.

**No connector/runtime implication**: Approving this claim row does not enable
any connector, registry, dialect, paper trading, or live execution.

---

### `policy_review:regional_legal_access_review`

**Classification**: `LEGAL_REVIEW_READY_FOR_OPERATOR_SIGNOFF`

**Evidence basis**:
- Research pack (Phase 26AR) summarizes the available public documentation.
- No automatic approval is possible — legal policy review requires
  explicit operator signoff with a defined scope and date.
- This row gates `B3` and the overall `evidence_review_complete` flag.

**Approval gate**: External operator legal signoff required. Cannot be
approved through automated evidence review. Proposal document produced in
Phase 26AT (`DERIBIT_OPERATOR_LEGAL_SIGNOFF_PROPOSAL_26AT.md`).

**No connector/runtime implication**: NONE.

---

### `policy_review:separate_connector_enablement`

**Classification**: `DEFER_SEPARATE_PHASE`

**Evidence basis**:
- The `separate_connector_enablement` row explicitly requires a dedicated
  `PUBLIC_MARKET_DATA_ONLY` connector-enablement phase.
- No evidence review, legal review, or operator approval in Phase 26AR-26AU
  can satisfy this row.
- `public_feed_dialects.py` and `static_registry_verified` remain unchanged.

**Action**: Defer. No action in this phase.

**No connector/runtime implication**: NONE.

---

## What Is NOT Done in This Proof Batch

- `regional_legal_access` is not yet approved — classification only.
- `regional_legal_access_review` is not approved — requires operator signoff.
- `separate_connector_enablement` is not approved — deferred.
- No connector enablement, no `public_feed_dialects.py` change.
- No `static_registry_verified` change.
- No private API, credentials, orders, or live execution.

---

## Evidence References

- `DERIBIT_REGIONAL_LEGAL_ACCESS_RESEARCH_PACK_26AR.md`
- `DERIBIT_CLAIM_REVIEW_WORKSHEET.md`
- `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md`
- `DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md`
