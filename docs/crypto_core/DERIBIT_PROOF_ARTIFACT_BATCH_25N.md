# Deribit Proof Artifact Batch - Phase 25N

- status: PROOF_ARTIFACT_BATCH_ONLY
- phase: 25N
- generated_at: 2026-05-17
- source_observed_artifact: `docs/crypto_core/DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`
- NOT_an_approval: true
- NOT_worksheet_mutation: true
- NOT_b1_b5_closure: true
- NOT_connector_enablement: true

## Summary

- already_approved_phase25i_count: 3
- approved_phase25r_change_id_count: 1
- new_proof_ready_not_approved_count: 0
- wait_insufficient_count: 6
- total_target_claims_in_this_batch: 7

The downloaded `deribit-public-smoke-proof` artifact from main run
`25671516104` contains actual `sample_events`. The accepted smoke result is
usable only under the strict PUBLIC_MARKET_DATA_ONLY boundary:
`dry_run=true`, `operator_authorization=PUBLIC_MARKET_DATA_ONLY`,
`accepted=true`, and `rejection_reasons=[]`.

Phase 25R update: the `change_id` worksheet row was subsequently approved
under `Phase25R_CHANGE_ID_ONLY` using the supplied operator metadata. The
strict evidence classification below remains the reason that row became
eligible; all other rows remain WAIT_INSUFFICIENT.

## Strict Classification Table

| claim_id | surface | classification | evidence_source | strict_reason |
|---|---|---|---|---|
| `public_websocket_availability` | claim_review | ALREADY_APPROVED_PHASE25I | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` | Already approved in Phase 25I; not changed here. |
| `unauthenticated_public_market_data` | claim_review | ALREADY_APPROVED_PHASE25I | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` | Already approved in Phase 25I; not changed here. |
| `orderbook_channel_feed` | claim_review | ALREADY_APPROVED_PHASE25I | `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` | Already approved in Phase 25I; not changed here. |
| `change_id` | claim_review | APPROVED_PHASE25R_CHANGE_ID_ONLY | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `change_id` | Actual observed Deribit sample events contain non-null integer `change_id` values and matching `sequence_id` values. Phase 25R approved this row only. |
| `prev_change_id` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json` | The observed sample events contain `prev_change_id=null` and `prev_sequence_id=null`; no actual non-null `prev_change_id` proof is committed. |
| `first_message_snapshot` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json` | The first observed sample event has `type=null` and `payload_kind=market_data`; it does not prove snapshot semantics. |
| `incremental_delta` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json` | The observed sample events have `type=null`; no observed `type=change` or explicit delta/change semantic proof is committed. |
| `continuity_condition` | claim_review | WAIT_INSUFFICIENT | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json` | Adjacent observed pairs cannot prove `prev_change_id[n] == change_id[n-1]` because all committed `prev_change_id` values are null. |
| `gap_resubscribe_rule` | claim_review | WAIT_INSUFFICIENT | none | No committed official documentation excerpt proves the gap recovery or resubscribe rule. |
| `heartbeat_liveness_proof` | claim_review | WAIT_INSUFFICIENT | none | No committed official documentation excerpt proves heartbeat, ping-pong, or liveness semantics. |

## Safety Invariants

- No worksheet row is edited.
- No final `APPROVE`, `REJECT`, or `DEFER` decision is written.
- No reviewer_id or reviewed_at_iso value is filled.
- `connector_ready_dialects()` must remain empty.
- B1-B5 remain BLOCKED.
- `public_feed_dialects.py` remains unchanged.

## Next Artifact Requirements

| blocked_claim | next_required_artifact |
|---|---|
| `prev_change_id` | Observed book proof containing non-null `prev_change_id` values. |
| `first_message_snapshot` | Observed first book event with explicit snapshot semantics or an official excerpt proving snapshotless aggregated book semantics. |
| `incremental_delta` | Observed book event proving delta/change semantics, or official excerpt resolving the `type=null` aggregated payload behavior. |
| `continuity_condition` | Adjacent observed event pair proving `prev_change_id[n] == change_id[n-1]`, or an official excerpt defining continuity for the channel shape observed. |
| `gap_resubscribe_rule` | Official notifications excerpt proving gap recovery or resubscribe requirements. |
| `heartbeat_liveness_proof` | Official environment/WebSocket excerpt proving heartbeat/liveness semantics. |
