# Deribit Proof Artifact Batch - Phase 25W

- status: PROOF_GAP_CLASSIFICATION_BATCH_ONLY
- phase: 25W
- generated_at: 2026-05-17
- source_observed_artifact: `docs/crypto_core/DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`
- source_gap_artifact: `docs/crypto_core/DERIBIT_ADJACENT_SEQUENCE_PROOF_GAP_25V.md`
- NOT_an_approval: true
- NOT_worksheet_mutation: true
- NOT_b1_b5_closure: true
- NOT_connector_enablement: true

## Summary

- already_approved_phase25i_count: 3
- approved_phase25r_change_id_count: 1
- newly_proof_ready_not_approved_count: 0
- wait_insufficient_count: 6
- total_classified_rows: 10

Phase 25V inspected the actual observed Phase 25M public book sample. The sample
contains adjacent events from the same channel, but each current event has
`prev_change_id=null`. This proves the gap, not the continuity claim. No
synthetic or harness-only values are used for classification.

## Strict Classification Table

| claim_id | surface | classification | evidence_source | strict_reason |
|---|---|---|---|---|
| `public_websocket_availability` | claim_review | ALREADY_APPROVED_PHASE25I | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` | Already approved in Phase 25I; not changed here. |
| `unauthenticated_public_market_data` | claim_review | ALREADY_APPROVED_PHASE25I | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` | Already approved in Phase 25I; not changed here. |
| `orderbook_channel_feed` | claim_review | ALREADY_APPROVED_PHASE25I | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` | Already approved in Phase 25I; not changed here. |
| `change_id` | claim_review | APPROVED_PHASE25R_CHANGE_ID_ONLY | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `change_id` | Actual observed events contain non-null integer `change_id`; Phase 25R approved this row only. |
| `prev_change_id` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_ADJACENT_SEQUENCE_PROOF_GAP_25V.md` | No actual current observed event has non-null `prev_change_id`; do not promote to PROOF_READY_NOT_APPROVED. |
| `continuity_condition` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_ADJACENT_SEQUENCE_PROOF_GAP_25V.md` | Adjacent observed pairs exist, but no pair proves `prev_change_id[current] == change_id[previous]` because all current `prev_change_id` values are null. |
| `first_message_snapshot` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json` | First observed event has `type=null`; snapshot semantics are not proven. |
| `incremental_delta` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json` | Observed events have `type=null`; delta/change semantics are not proven. |
| `gap_resubscribe_rule` | claim_review | WAIT_INSUFFICIENT | none | No committed official documentation excerpt proves the gap recovery or resubscribe rule. |
| `heartbeat_liveness_proof` | claim_review | WAIT_INSUFFICIENT | none | No committed official environment or heartbeat excerpt proves heartbeat, ping-pong, or liveness semantics. |

## Explicit Non-Promotion Rules

- `prev_change_id` becomes PROOF_READY_NOT_APPROVED only when an actual observed
  current event has non-null `prev_change_id`.
- `continuity_condition` becomes PROOF_READY_NOT_APPROVED only when an actual
  adjacent observed pair proves `current.prev_change_id == prior.change_id`.
- `first_message_snapshot` remains WAIT_INSUFFICIENT unless the first observed
  event proves snapshot semantics or an official excerpt explains the observed
  channel behavior.
- `incremental_delta` remains WAIT_INSUFFICIENT unless an observed event proves
  delta/change semantics or an official excerpt explains the observed channel
  behavior.
- `gap_resubscribe_rule` remains WAIT_INSUFFICIENT until an official
  notifications excerpt is committed.
- `heartbeat_liveness_proof` remains WAIT_INSUFFICIENT until an official
  environment or heartbeat excerpt is committed.

## Safety Invariants

- No worksheet row is edited.
- No final `APPROVE`, `REJECT`, or `DEFER` decision is written.
- No reviewer_id or reviewed_at_iso value is filled.
- No Phase 25X operator-fill proposal is created because no row is newly
  proof-ready.
- `connector_ready_dialects()` must remain empty.
- B1-B5 remain BLOCKED.
- `public_feed_dialects.py` remains unchanged.
