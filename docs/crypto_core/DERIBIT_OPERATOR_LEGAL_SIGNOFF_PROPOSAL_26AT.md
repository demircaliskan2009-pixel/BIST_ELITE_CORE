# Deribit Operator Legal Signoff Proposal (Phase 26AT)

status: OPERATOR_SIGNOFF_PROPOSAL
phase: 26AT
reviewed_at_iso: 2026-05-19T00:00:00Z
target_row: policy_review:regional_legal_access_review
surface: policy_review

---

## Purpose

This proposal document provides the operator with a structured framework
for completing the manual legal signoff required for the
`regional_legal_access_review` policy row.

It does not constitute a signoff itself. The operator must supply
`reviewer_id`, `reviewed_at_iso`, and an explicit `scope` before the row
can be approved in the policy worksheet.

---

## Signoff Template

The following fields are required in
`DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md`
for the `regional_legal_access_review` row:

```
reviewer_id=<OPERATOR_REQUIRED>
reviewed_at_iso=<OPERATOR_REQUIRED>
decision=SIGNOFF_CANDIDATE
scope=<OPERATOR_REQUIRED>
```

---

## Row Under Review

| field | current value | required value |
|---|---|---|
| `policy_id` | `regional_legal_access_review` | unchanged |
| `venue_id` | `deribit` | unchanged |
| `policy_status` | `PENDING` | `APPROVED` (after signoff) |
| `policy_blocker_status` | `MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED` | operator-defined |
| `reviewer_id` | `PENDING` | `<OPERATOR_REQUIRED>` |
| `reviewed_at_iso` | `PENDING` | `<OPERATOR_REQUIRED>` |
| `decision` | `PENDING` | `APPROVED` (after signoff) |

---

## Evidence Available to Operator

1. **Phase 26AR Research Pack**: `DERIBIT_REGIONAL_LEGAL_ACCESS_RESEARCH_PACK_26AR.md`
   - Turkey not listed in restricted jurisdictions (Phase 22L snapshot)
   - Unauthenticated public API documented
   - Market data personal-use limitation noted
   - No Turkey-specific legal clearance found

2. **Phase 26AS Proof Batch**: `DERIBIT_REGIONAL_LEGAL_ACCESS_PROOF_BATCH_26AS.md`
   - Classification of all three pending rows
   - No connector/runtime implication for any row

3. **Phase 22L Source Snapshot**:
   - `source_sha256: a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd`
   - Deribit documentation payload as of 2026-05-10

---

## Constraints

The operator signoff is subject to the following hard constraints:

1. The signoff applies only to `PUBLIC_MARKET_DATA_ONLY` access.
2. No private API, no credentials, no order submission.
3. Market data use is restricted to personal use per Deribit ToS unless
   prior written Deribit approval is obtained.
4. No connector enablement, no `public_feed_dialects.py` change.
5. No `static_registry_verified` change.
6. The `separate_connector_enablement` row is NOT covered by this signoff.

---

## Effect on Validator After Operator Signoff

When the operator completes the signoff and approves
`regional_legal_access_review` in the policy worksheet:

```
pending_rows: 1  (only separate_connector_enablement)
accepted: False
evidence_review_complete: False
connector_enablement_ready: False
B1-B5: all BLOCKED
```

This is an EXTERNAL engineering gate. No automated system can trigger
the signoff.

---

## What Is NOT Changed in Phase 26AT

- `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md` is NOT edited.
- `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` is patched for `regional_legal_access`
  (claim row only, not policy row).
- No connector, no `public_feed_dialects.py`, no live integration.
- `separate_connector_enablement` remains PENDING/DEFERRED.

---

## Evidence References

- `DERIBIT_REGIONAL_LEGAL_ACCESS_RESEARCH_PACK_26AR.md`
- `DERIBIT_REGIONAL_LEGAL_ACCESS_PROOF_BATCH_26AS.md`
- `DERIBIT_CLAIM_REVIEW_WORKSHEET.md`
- `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md`
