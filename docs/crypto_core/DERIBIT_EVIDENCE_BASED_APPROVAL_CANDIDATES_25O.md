# Deribit Evidence Based Approval Candidates - Phase 25O

status: OPERATOR_DECISION_CANDIDATES_ONLY

This file is an operator decision candidate package only. It does not mutate
the real worksheets, does not write final APPROVE/REJECT/DEFER decisions, does
not approve B1-B5, and does not change connector readiness.

## Summary

- already_approved_phase25i_claim_count: 3
- newly_proof_ready_not_approved_claim_count: 1
- total_claim_candidates_listed: 4
- worksheet_edits: NONE
- reviewer_metadata_supplied: NO
- connector_ready_dialects_effect: NONE

## Candidate Table

| bucket | surface | row_id | source_id | current_status | exact_evidence_refs | operator_note |
|---|---|---|---|---|---|---|
| ALREADY_APPROVED_PHASE25I | claim_review | `public_websocket_availability` | `DERIBIT_ENVIRONMENT` | APPROVED | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `public_websocket_availability`; `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md` | Already approved by operator in Phase 25I; repeated here only for package continuity. |
| ALREADY_APPROVED_PHASE25I | claim_review | `unauthenticated_public_market_data` | `DERIBIT_ENVIRONMENT` | APPROVED | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `unauthenticated_public_market_data`; `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md` | Already approved by operator in Phase 25I; repeated here only for package continuity. |
| ALREADY_APPROVED_PHASE25I | claim_review | `orderbook_channel_feed` | `DERIBIT_NOTIFICATIONS` | APPROVED | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `orderbook_channel_feed`; `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md` | Already approved by operator in Phase 25I; repeated here only for package continuity. |
| PROOF_READY_NOT_APPROVED | claim_review | `change_id` | `DERIBIT_NOTIFICATIONS` | PENDING | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_PROOF_ARTIFACT_BATCH_25N.md` | Newly proof-ready because actual observed Deribit book sample events contain non-null integer `change_id` values. Operator approval still requires explicit reviewer_id and reviewed_at_iso in a later worksheet patch. |

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
