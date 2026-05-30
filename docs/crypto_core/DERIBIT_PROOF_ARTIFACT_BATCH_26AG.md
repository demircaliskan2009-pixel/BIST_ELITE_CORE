# Deribit Proof Artifact Batch - Phase 26AG

status: CLASSIFICATION_BATCH_ONLY
phase: 26AG
generated_at: 2026-05-18
research_pack: DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md
proof_batch: DERIBIT_OFFICIAL_DOCS_PROOF_BATCH_26AF.md
NOT_an_approval: true
NOT_worksheet_mutation: true
NOT_connector_enablement: true
NOT_b1_b5_closure: true
NOT_legal_approval: true

## Purpose

Phase 26AG translates the official documentation research pack into
fail-closed claim classifications. It does not edit the real Deribit claim
worksheet. It records that 15 rows are proof-ready for operator review, one
legal/access row has documentation proof only, and the validator remains
blocked because no final worksheet approvals were supplied.

## Classification Results

### PROOF_READY_NOT_APPROVED: 15

| row_id | prior_status | new_classification | evidence |
|---|---|---|---|
| `claim_review:public_rest_availability` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` refs `S2_JSON_RPC_TRANSPORTS`, `S5_REST_ORDER_BOOK`; `26AF` proof batch row. |
| `claim_review:prod_testnet_ws_endpoint` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` refs `S1_ENVIRONMENTS`, `S2_JSON_RPC_TRANSPORTS`; `26AF` proof batch row. |
| `claim_review:prod_testnet_rest_endpoint` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` refs `S1_ENVIRONMENTS`, `S2_JSON_RPC_TRANSPORTS`; `26AF` proof batch row. |
| `claim_review:rest_snapshot_requirement` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` refs `S4_NOTIFICATIONS_RELIABILITY`, `S5_REST_ORDER_BOOK`; `26AF` proof batch row. |
| `claim_review:gap_resubscribe_rule` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` ref `S4_NOTIFICATIONS_RELIABILITY`; `26AF` proof batch row. |
| `claim_review:heartbeat_liveness_proof` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` ref `S6_HEARTBEAT`; `26AF` proof batch row. |
| `claim_review:public_rate_subscription_limits` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` ref `S7_RATE_LIMITS`; `26AF` proof batch row. |
| `claim_review:public_trades` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` ref `S8_TRADES_CHANNEL`; `26AF` proof batch row. |
| `claim_review:ticker` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` ref `S9_TICKER_CHANNEL`; `26AF` proof batch row. |
| `claim_review:mark_index_funding_open_interest` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` ref `S9_TICKER_CHANNEL`; `26AF` proof batch row. |
| `claim_review:testnet_prod_difference` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` refs `S1_ENVIRONMENTS`, `S2_JSON_RPC_TRANSPORTS`; `26AF` proof batch row. |
| `claim_review:first_message_snapshot` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` refs `S3_BOOK_CHANNEL`, `S4_NOTIFICATIONS_RELIABILITY`; `26AF` proof batch row. |
| `claim_review:incremental_delta` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` ref `S3_BOOK_CHANNEL`; `26AF` proof batch row. |
| `claim_review:prev_change_id` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` refs `S3_BOOK_CHANNEL`, `S4_NOTIFICATIONS_RELIABILITY`; `26AF` proof batch row. |
| `claim_review:continuity_condition` | `WAIT_INSUFFICIENT` | `PROOF_READY_NOT_APPROVED` | `26AE` refs `S3_BOOK_CHANNEL`, `S4_NOTIFICATIONS_RELIABILITY`; `26AF` proof batch row. |

### DOCUMENTATION_PROOF_READY: 1

| row_id | prior_status | new_classification | evidence | approval_effect |
|---|---|---|---|---|
| `claim_review:regional_legal_access` | `WAIT_LEGAL` | `DOCUMENTATION_PROOF_READY` | `26AE` ref `S10_RESTRICTED_JURISDICTIONS`; `26AF` proof batch row. | `NO_LEGAL_APPROVAL` |

### Still Fail-Closed

| row_id | classification | reason |
|---|---|---|
| `claim_review:checksum_decision` | `WAIT_INSUFFICIENT` | Not researched in Phase 26AE and no official checksum evidence is cited. |
| `claim_review:staleness_budget` | `WAIT_POLICY` | Requires operator policy value. |
| `claim_review:receive_lag_budget` | `WAIT_POLICY` | Requires operator policy value. |
| `policy_review:checksum_decision` | `WAIT_POLICY` | Depends on checksum claim and policy decision. |
| `policy_review:liveness_policy` | `WAIT_POLICY` | Depends on heartbeat claim review plus policy decision. |
| `policy_review:staleness_budget` | `WAIT_POLICY` | Requires operator policy value. |
| `policy_review:receive_lag_budget` | `WAIT_POLICY` | Requires operator policy value. |
| `policy_review:testnet_prod_review` | `WAIT_POLICY` | Depends on environment proof plus operator review. |
| `policy_review:regional_legal_access_review` | `WAIT_LEGAL` | Requires human legal review. |
| `policy_review:separate_connector_enablement` | `WAIT_POLICY` | Deferred to separate authorization after all blockers resolve. |

## Validator and Connector Effect

| metric | value |
|---|---|
| `pending_rows` | 26 |
| `accepted` | False |
| `evidence_review_complete` | False |
| `ready_for_engineering_patch` | False |
| `connector_enablement_ready` | False |
| `connector_ready_dialects()` | `()` |
| `B1-B5` | `BLOCKED` |

The worksheet remains pending because no final operator reviewer_id,
reviewed_at_iso, or approval decision was provided.
