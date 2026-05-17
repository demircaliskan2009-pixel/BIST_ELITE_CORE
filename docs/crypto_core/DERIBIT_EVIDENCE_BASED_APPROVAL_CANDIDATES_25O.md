# Deribit Evidence Based Approval Candidates - Phase 25O

status: OPERATOR_DECISION_CANDIDATES_ONLY

This file is an operator decision candidate package only. It does not mutate
the real worksheets, does not write final APPROVE/REJECT/DEFER decisions, does
not approve B1-B5, and does not change connector readiness.

Phase 25R update: the operator supplied exact metadata for the `change_id`
candidate only (`reviewer_id=demir_operator`,
`reviewed_at_iso=2026-05-11T00:00:00Z`,
`approval_scope=Phase25R_CHANGE_ID_ONLY`). The real worksheet now records
`change_id` as APPROVED. This does not approve any other row and does not
change connector readiness.

## Summary

- already_approved_phase25i_claim_count: 3
- newly_approved_phase25r_claim_count: 1
- newly_proof_ready_not_approved_claim_count: 0
- total_claim_candidates_listed: 4
- worksheet_edits: CHANGE_ID_ONLY
- reviewer_metadata_supplied: YES_CHANGE_ID_ONLY
- connector_ready_dialects_effect: NONE

## Candidate Table

| bucket | surface | row_id | source_id | current_status | exact_evidence_refs | operator_note |
|---|---|---|---|---|---|---|
| ALREADY_APPROVED_PHASE25I | claim_review | `public_websocket_availability` | `DERIBIT_ENVIRONMENT` | APPROVED | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `public_websocket_availability`; `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md` | Already approved by operator in Phase 25I; repeated here only for package continuity. |
| ALREADY_APPROVED_PHASE25I | claim_review | `unauthenticated_public_market_data` | `DERIBIT_ENVIRONMENT` | APPROVED | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `unauthenticated_public_market_data`; `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md` | Already approved by operator in Phase 25I; repeated here only for package continuity. |
| ALREADY_APPROVED_PHASE25I | claim_review | `orderbook_channel_feed` | `DERIBIT_NOTIFICATIONS` | APPROVED | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `orderbook_channel_feed`; `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md` | Already approved by operator in Phase 25I; repeated here only for package continuity. |
| APPROVED_PHASE25R_CHANGE_ID_ONLY | claim_review | `change_id` | `DERIBIT_NOTIFICATIONS` | APPROVED | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_PROOF_ARTIFACT_BATCH_25N.md`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `change_id` | Approved only for the `change_id` row using supplied operator metadata. This does not approve `prev_change_id`, snapshot, delta, continuity, policy, legal, or connector enablement rows. |

## Rows Not Added As Approval Candidates

| row_id | reason |
|---|---|
| `prev_change_id` | Observed sample events contain `prev_change_id=null`; still WAIT_INSUFFICIENT. |
| `first_message_snapshot` | Observed first event has `type=null`; snapshot semantics not proven. |
| `incremental_delta` | Observed events have `type=null`; delta/change semantics not proven. |
| `continuity_condition` | Cannot prove continuity because committed `prev_change_id` values are null. |
| `gap_resubscribe_rule` | Requires official documentation excerpt. |
| `heartbeat_liveness_proof` | Requires official documentation excerpt and liveness policy approval. |
| policy rows | No policy values or legal review were supplied in this prompt. |
| `separate_connector_enablement` | Must remain deferred to a separate explicit connector-enablement phase. |
