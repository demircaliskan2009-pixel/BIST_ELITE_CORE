# Deribit Proof Artifact Batch — Phase 25K

- status: PROOF_ARTIFACT_BATCH_ONLY
- phase: 25K
- baseline_commit: a1f931d54d466a43ee2c8d9dc784b88fe63a35ef
- batch_date: 2026-05-11

## Summary Metadata

- batch_status: PROOF_ARTIFACT_BATCH_ONLY
- NOT_an_approval: true
- NOT_worksheet_mutation: true
- NOT_b1_b5_closure: true
- NOT_connector_enablement: true
- already_approved_phase25i_count: 3
- proof_ready_not_approved_count: 0
- wait_insufficient_count: 7
- harness_capability_records_count: 5
- total_target_claims_in_this_batch: 10

## Safety Statement

This document:

- does NOT approve any worksheet row
- does NOT mutate DERIBIT_CLAIM_REVIEW_WORKSHEET.md
- does NOT mutate DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md
- does NOT change B1-B5 status
- does NOT change validator outputs
- does NOT enable connector_ready_dialects
- does NOT fill reviewer_id or reviewed_at_iso in any row
- is read-only over committed documentation and harness source files
- is a batch classification of what committed in-repo evidence supports
- harness capability records are advisory documentation only; they are not approvals
- the proof_ready_not_approved classification means committed evidence exists for
  human operator review; it does NOT constitute a worksheet approval

## Baseline Validator State

- accepted: false
- evidence_review_complete: false
- ready_for_engineering_patch: false
- connector_enablement_ready: false
- pending_rows_count: 27
- connector_ready_dialects_count: 0
- b1_b5_status: B1=BLOCKED, B2=BLOCKED, B3=BLOCKED, B4=BLOCKED, B5=BLOCKED

## Batch Claim Classification Table

| claim_id | surface | classification | evidence_source | gap_reason |
|---|---|---|---|---|
| `public_websocket_availability` | claim_review | ALREADY_APPROVED_PHASE25I | DERIBIT_CLAIM_REVIEW_WORKSHEET.md decision=APPROVED Phase25I | Approved by human operator in Phase 25I; not re-classified in this batch. |
| `unauthenticated_public_market_data` | claim_review | ALREADY_APPROVED_PHASE25I | DERIBIT_CLAIM_REVIEW_WORKSHEET.md decision=APPROVED Phase25I | Approved by human operator in Phase 25I; not re-classified in this batch. |
| `orderbook_channel_feed` | claim_review | ALREADY_APPROVED_PHASE25I | DERIBIT_CLAIM_REVIEW_WORKSHEET.md decision=APPROVED Phase25I | Approved by human operator in Phase 25I; not re-classified in this batch. |
| `change_id` | claim_review | WAIT_INSUFFICIENT | deribit_public_ws_harness.py _sequence_id_from_data() reads change_id field (advisory capability record only) | Harness code is design evidence only; no committed parse-sequence artifact proves actual change_id integer values from a real message sequence. Requires DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json. |
| `prev_change_id` | claim_review | WAIT_INSUFFICIENT | deribit_public_ws_harness.py _prev_sequence_id_from_data() reads prev_change_id field (advisory capability record only) | Harness code is design evidence only; no committed parse-sequence artifact proves actual prev_change_id values or that prev_change_id[n] equals change_id[n-1]. Requires DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json. |
| `first_message_snapshot` | claim_review | WAIT_INSUFFICIENT | deribit_public_ws_harness.py _payload_kind() reads type field (advisory capability record only) | No committed artifact proves first message has type equal to snapshot. Harness design documents intent; actual field values not committed to repo. Requires DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json. |
| `incremental_delta` | claim_review | WAIT_INSUFFICIENT | deribit_public_ws_harness.py _payload_kind() reads type field (advisory capability record only) | No committed artifact proves subsequent messages carry type equal to change with populated delta entries. Harness design is advisory only. Requires DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json. |
| `continuity_condition` | claim_review | WAIT_INSUFFICIENT | Depends on change_id and prev_change_id committed field-value proof | No committed artifact proves prev_change_id[n] equals change_id[n-1] across a real message sequence. Requires DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json. |
| `gap_resubscribe_rule` | claim_review | WAIT_INSUFFICIENT | None; DERIBIT_NOTIFICATIONS source snapshot hashed but section not excerpted | No committed official doc excerpt proves gap recovery or resubscribe semantics. Requires DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md. |
| `heartbeat_liveness_proof` | claim_review | WAIT_INSUFFICIENT | deribit_public_ws_harness.py _is_control_payload() handles method heartbeat (advisory capability record only) | No committed doc excerpt proves official heartbeat interval or liveness policy semantics. Harness control-payload handling is design evidence only. Requires DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md. |

## Harness Capability Records (Advisory — Not Approvals)

These records document committed harness source code design that is relevant to
pending claim rows. They are advisory evidence only. They do NOT approve any
worksheet row. They do NOT constitute parse-sequence artifacts, official-doc
excerpts, or human-verified field values.

| capability_id | harness_function | file_location | design_evidence |
|---|---|---|---|
| `payload_kind_from_type` | `_payload_kind(data)` | `src/crypto_core/data/deribit_public_ws_harness.py` | Returns data.get type — harness design expects Deribit book notifications to include a type field with values snapshot and change. |
| `sequence_id_from_change_id` | `_sequence_id_from_data(data)` | `src/crypto_core/data/deribit_public_ws_harness.py` | Reads change_id as first-priority field, then sequence, then seq — maps to sequence_id. Harness design expects Deribit book notifications to include change_id. |
| `prev_sequence_id_from_prev_change_id` | `_prev_sequence_id_from_data(data)` | `src/crypto_core/data/deribit_public_ws_harness.py` | Reads prev_change_id as first-priority field, then prev_sequence, then prev_seq — maps to prev_sequence_id. Harness design expects prev_change_id in Deribit book notifications. |
| `control_payload_detection` | `_is_control_payload(config, payload)` | `src/crypto_core/data/deribit_public_ws_harness.py` | Detects method in the set of heartbeat and test_request as control payloads, not market data. Harness design is aware of Deribit liveness protocol. |
| `payload_sample_captures_change_id` | `_payload_sample(data)` | `src/crypto_core/data/deribit_public_ws_harness.py` | Captures type, instrument_name, timestamp, change_id, and prev_change_id in every event sample. Both sequence fields are explicitly present in the sample schema. |

## Validator Invariants (Must Remain Unchanged)

These invariants must hold throughout Phase 25K and must not be modified by this batch.

| invariant | expected_value |
|---|---|
| `accepted` | `false` |
| `evidence_review_complete` | `false` |
| `ready_for_engineering_patch` | `false` |
| `connector_enablement_ready` | `false` |
| `pending_rows_count` | `27` |
| `manifest_reviewed_approved_count` | `6` |
| `claim_approved_count` | `3` |
| `policy_approved_count` | `0` |
| `connector_ready_dialects_count` | `0` |
| `b1_status` | `BLOCKED` |
| `b2_status` | `BLOCKED` |
| `b3_status` | `BLOCKED` |
| `b4_status` | `BLOCKED` |
| `b5_status` | `BLOCKED` |

## Next Phase Requirements

The following artifacts are required before additional worksheet approvals can proceed:

1. `DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json` — committed fixture recording actual
   type, change_id, and prev_change_id field values from a real Deribit book
   channel message sequence. Required for: first_message_snapshot,
   incremental_delta, change_id (confirmation), prev_change_id (confirmation),
   continuity_condition.

2. `DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md` — committed official doc
   excerpt from the notifications section. Required for: gap_resubscribe_rule,
   rest_snapshot_requirement.

3. `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md` — committed official doc
   excerpt from the environment or WebSocket section. Required for:
   heartbeat_liveness_proof.
