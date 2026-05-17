# Deribit Operator Fill Proposal - Phase 25P

status: PROPOSAL_ONLY_NOT_APPLIED

This proposal is not a worksheet edit. It does not apply final approvals and it
does not supply reviewer metadata. The operator must provide exact
`reviewer_id` and `reviewed_at_iso` values before any real worksheet patch can
be made.

## Proposal Rows

| surface | row_id | proposed_decision | reviewer_id | reviewed_at_iso | evidence_refs | scope_note |
|---|---|---|---|---|---|---|
| claim_review | `change_id` | APPROVE_CANDIDATE | `<OPERATOR_REQUIRED>` | `<OPERATOR_REQUIRED>` | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_PROOF_ARTIFACT_BATCH_25N.md`; `DERIBIT_EVIDENCE_BASED_APPROVAL_CANDIDATES_25O.md` | Actual observed Deribit book sample events contain non-null integer `change_id` values. This proposal does not approve the row. |

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

- worksheet_edits: NONE
- final_approvals: NONE
- connector_enablement: NONE
- connector_ready_dialects_effect: NONE
- b1_b5_effect: LEAVES_BLOCKED
