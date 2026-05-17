# Deribit Operator Fill Proposal - Phase 25P

status: SUPERSEDED_BY_PHASE25R_CHANGE_ID_APPROVAL

This proposal began as a worksheet-fill proposal, not a worksheet edit. Phase
25R later supplied exact operator metadata for `change_id` only; all other rows
in this file remain proposal-only and require separate operator metadata before
any real worksheet patch can be made.

Phase 25R update: exact operator metadata was supplied for `change_id` only,
and the real claim worksheet now records that single row as APPROVED under
`Phase25R_CHANGE_ID_ONLY`. This file remains a historical proposal record and
does not approve any other row.

## Proposal Rows

| surface | row_id | proposed_decision | reviewer_id | reviewed_at_iso | evidence_refs | scope_note |
|---|---|---|---|---|---|---|
| claim_review | `change_id` | APPROVED_PHASE25R_CHANGE_ID_ONLY | `demir_operator` | `2026-05-11T00:00:00Z` | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_PROOF_ARTIFACT_BATCH_25N.md`; `DERIBIT_EVIDENCE_BASED_APPROVAL_CANDIDATES_25O.md`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `change_id` | Actual observed Deribit book sample events contain non-null integer `change_id` values. Phase 25R approved this row only. |

## Explicit Non-Proposals

- `prev_change_id`: no non-null observed value committed.
- `first_message_snapshot`: no observed snapshot type committed.
- `incremental_delta`: no observed change/delta type committed.
- `continuity_condition`: no adjacent pair proves `prev_change_id[n] == change_id[n-1]`.
- `gap_resubscribe_rule`: official excerpt still missing.
- `heartbeat_liveness_proof`: official excerpt and liveness policy still missing.
- all operational policy rows: no policy values supplied.
- `separate_connector_enablement`: remains a separate deferred phase.

## Safety State

- worksheet_edits: CHANGE_ID_ONLY_BY_PHASE25R
- final_approvals: CHANGE_ID_ONLY
- connector_enablement: NONE
- connector_ready_dialects_effect: NONE
- b1_b5_effect: LEAVES_BLOCKED
