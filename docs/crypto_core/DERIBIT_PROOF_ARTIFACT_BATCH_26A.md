# Deribit Proof Artifact Batch - Phase 26A

- status: PROOF_GAP_CLASSIFICATION_BATCH_ONLY
- phase: 26A
- generated_at: 2026-05-17
- source_capture_spec: `docs/crypto_core/DERIBIT_NON_NULL_PREV_CHANGE_ID_CAPTURE_SPEC_25Z.md`
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
- proposal_26b_created: NO

Phase 26A found no committed actual artifact with a non-null
`prev_change_id`. The only committed observed sequence artifact remains Phase
25M, where all observed `prev_change_id` and `prev_sequence_id` values are null.
Therefore `prev_change_id` and `continuity_condition` remain
WAIT_INSUFFICIENT.

## Strict Classification Table

| claim_id | surface | classification | evidence_source | strict_reason |
|---|---|---|---|---|
| `public_websocket_availability` | claim_review | ALREADY_APPROVED_PHASE25I | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` | Already approved in Phase 25I; not changed here. |
| `unauthenticated_public_market_data` | claim_review | ALREADY_APPROVED_PHASE25I | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` | Already approved in Phase 25I; not changed here. |
| `orderbook_channel_feed` | claim_review | ALREADY_APPROVED_PHASE25I | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` | Already approved in Phase 25I; not changed here. |
| `change_id` | claim_review | APPROVED_PHASE25R_CHANGE_ID_ONLY | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `change_id` | Actual observed events contain non-null integer `change_id`; Phase 25R approved this row only. |
| `prev_change_id` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_ADJACENT_SEQUENCE_PROOF_GAP_25V.md`; `DERIBIT_NON_NULL_PREV_CHANGE_ID_CAPTURE_SPEC_25Z.md` | `non_null_prev_change_id_observed=false`; no actual observed current event has non-null `prev_change_id`. |
| `continuity_condition` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_ADJACENT_SEQUENCE_PROOF_GAP_25V.md`; `DERIBIT_NON_NULL_PREV_CHANGE_ID_CAPTURE_SPEC_25Z.md` | `continuity_pair_missing=true`; no adjacent pair proves `current.prev_change_id == prior.change_id`. |
| `first_message_snapshot` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json` | First observed event has `type=null`; snapshot semantics are not proven. |
| `incremental_delta` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json` | Observed events have `type=null`; delta/change semantics are not proven. |
| `gap_resubscribe_rule` | claim_review | WAIT_INSUFFICIENT | none | No committed official documentation excerpt proves the gap recovery or resubscribe rule. |
| `heartbeat_liveness_proof` | claim_review | WAIT_INSUFFICIENT | none | No committed official environment or heartbeat excerpt proves heartbeat, ping-pong, or liveness semantics. |

## Non-Promotion Evidence

| evidence_check | result | effect |
|---|---|---|
| actual artifact with non-null `prev_change_id` exists in repo | false | `prev_change_id` remains WAIT_INSUFFICIENT. |
| newly captured CI artifact with non-null `prev_change_id` is committed | false | `prev_change_id` remains WAIT_INSUFFICIENT. |
| adjacent pair equality `current.prev_change_id == prior.change_id` is proven | false | `continuity_condition` remains WAIT_INSUFFICIENT. |
| non-null but mismatched `prev_change_id` is present | false | No continuity promotion; future mismatch must be recorded as a gap. |

## Safety Invariants

- No worksheet row is edited.
- No final `APPROVE`, `REJECT`, or `DEFER` decision is written.
- No reviewer_id or reviewed_at_iso value is filled.
- No Phase 26B operator-fill proposal is created because zero rows are newly
  proof-ready.
- `connector_ready_dialects()` must remain empty.
- B1-B5 remain BLOCKED.
- `public_feed_dialects.py` remains unchanged.
