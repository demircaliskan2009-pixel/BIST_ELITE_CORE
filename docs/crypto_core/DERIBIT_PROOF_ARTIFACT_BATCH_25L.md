# Deribit Proof Artifact Batch — Phase 25L

- status: PROOF_ARTIFACT_BATCH_ONLY
- phase: 25L
- baseline_commit: 0334de43f0c4cfd530619b98ae5d5585c9211c08
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
- total_target_claims_in_this_batch: 7

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
- PROOF_READY_NOT_APPROVED means committed code + test evidence exists for human
  operator review; it does NOT constitute a worksheet approval
- the proof fixture DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json is a DETERMINISTIC_HARNESS_FIXTURE —
  it documents committed harness field-mapping logic, NOT live observed integer values

## Phase 25K Inherited State

- Phase 25I approved: public_websocket_availability, unauthenticated_public_market_data, orderbook_channel_feed (3 claims)
- Phase 25K result: all 7 non-approved claims = WAIT_INSUFFICIENT; proof_ready_not_approved_count=0
- Phase 25L adds: DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json as a HARNESS_CAPABILITY_ADVISORY_ONLY fixture; change_id and prev_change_id remain WAIT_INSUFFICIENT (harness code design is not parse-sequence proof)

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
| `change_id` | claim_review | WAIT_INSUFFICIENT | DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json (HARNESS_CAPABILITY_ADVISORY_ONLY) | Harness code design is advisory only. No committed artifact records actual observed change_id integer values from a real Deribit server message. Same standard applied in Phase 25K Codex P2 review. Requires committed parse-sequence fixture with actual observed change_id values. |
| `prev_change_id` | claim_review | WAIT_INSUFFICIENT | DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json (HARNESS_CAPABILITY_ADVISORY_ONLY) | Harness code design is advisory only. No committed artifact records actual observed prev_change_id integer values from a real Deribit server message. Same standard applied in Phase 25K Codex P2 review. Requires committed parse-sequence fixture with actual observed prev_change_id values. |
| `first_message_snapshot` | claim_review | WAIT_INSUFFICIENT | DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json documents gap: no committed artifact records actual observed type=snapshot from Deribit server | Harness _payload_kind() reads type field; test fixture uses type=snapshot. But no committed artifact records actual observed type field values from the 19 smoke run messages. Requires committed parse-sequence fixture with observed type=snapshot. |
| `incremental_delta` | claim_review | WAIT_INSUFFICIENT | DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json documents gap: no committed artifact records actual observed type=change from Deribit server | Same gap as first_message_snapshot — no committed artifact proves subsequent messages carry type=change with populated delta entries. Requires committed parse-sequence fixture with observed type=change. |
| `continuity_condition` | claim_review | WAIT_INSUFFICIENT | DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json documents gap: no committed artifact proves prev_change_id[n]==change_id[n-1] across actual received messages | Harness implements and tests the continuity check, but no committed record proves this held across the 19 smoke run messages. Requires committed parse-sequence fixture recording actual change_id and prev_change_id values in sequence. |
| `gap_resubscribe_rule` | claim_review | WAIT_INSUFFICIENT | None; no official doc excerpt committed | No committed official doc excerpt proves gap recovery or resubscribe semantics. Requires DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md. |
| `heartbeat_liveness_proof` | claim_review | WAIT_INSUFFICIENT | harness _is_control_payload() handles method=heartbeat (advisory capability record only) | No committed doc excerpt proves official heartbeat interval or liveness policy semantics. Harness control-payload handling is design evidence only. Requires DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md. |

## Phase 25L Harness Capability Records (Advisory — Not Approvals)

The following harness capability records are documented by `DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json`
as `HARNESS_CAPABILITY_ADVISORY_ONLY`. They are NOT parse-sequence proof artifacts and do NOT
constitute worksheet evidence for claim approval.

### `change_id` — WAIT_INSUFFICIENT

Harness capability record (advisory only):
- `_sequence_id_from_data()` reads `data.get("change_id")` as first-priority field
- `_payload_sample()` includes `"change_id"` in every event sample dict
- Test fixture uses `change_id=10` (synthetic value, NOT observed from Deribit server)
- Smoke run (Phase 23L, 19 messages, 0 rejections) ran code paths without error but
  field-level integer values were NOT committed to this repo

Gap: No committed artifact records actual observed `change_id` integer values from a real
Deribit server message. Harness code design alone is insufficient (same standard enforced
in Phase 25K Codex P2 review).

### `prev_change_id` — WAIT_INSUFFICIENT

Harness capability record (advisory only):
- `_prev_sequence_id_from_data()` reads `data.get("prev_change_id")` as first-priority field
- `_event_from_payload()` uses `prev_sequence_id` in sequence-gap continuity check
- Test fixture uses `prev_change_id=9` (synthetic value, NOT observed from Deribit server)
- Smoke run (Phase 23L, 0 rejections) confirms the check ran without fault but field-level
  values were NOT committed to this repo

Gap: No committed artifact records actual observed `prev_change_id` integer values from a
real Deribit server message. Harness code design alone is insufficient.

## Remaining WAIT_INSUFFICIENT Claims (7 total)

- `change_id`: Requires committed parse-sequence fixture with actual observed `change_id` integer values from Deribit server.
- `prev_change_id`: Requires committed parse-sequence fixture with actual observed `prev_change_id` integer values from Deribit server.
- `first_message_snapshot`: Requires committed artifact with actual observed `type="snapshot"` from Deribit server.
- `incremental_delta`: Requires committed artifact with actual observed `type="change"` from Deribit server.
- `continuity_condition`: Requires committed artifact proving `prev_change_id[n] == change_id[n-1]` across real message sequence.
- `gap_resubscribe_rule`: Requires `DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md`.
- `heartbeat_liveness_proof`: Requires `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md`.

## Validator Invariants (Must Remain Unchanged)

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

1. Committed parse-sequence fixture recording actual observed `type`, `change_id`, `prev_change_id`
   integer values from a real Deribit book channel message sequence — required for:
   `change_id`, `prev_change_id`, `first_message_snapshot`, `incremental_delta`, `continuity_condition`.

2. `DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md` — official doc excerpt — required for:
   `gap_resubscribe_rule`, `rest_snapshot_requirement`.

3. `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md` — official doc excerpt — required for:
   `heartbeat_liveness_proof`.
