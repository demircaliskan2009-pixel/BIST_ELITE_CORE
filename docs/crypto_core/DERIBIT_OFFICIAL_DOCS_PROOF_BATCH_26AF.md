# Deribit Official Docs Proof Batch - Phase 26AF

status: OFFICIAL_DOCS_PROOF_BATCH_ONLY
phase: 26AF
generated_at: 2026-05-18
source_pack: DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md
NOT_an_approval: true
NOT_worksheet_mutation: true
NOT_connector_enablement: true
NOT_b1_b5_closure: true
NOT_legal_approval: true

## Classification Rule

Rows are promoted only when Phase 26AE cites current official Deribit evidence
with a URL/anchor and section title. Ambiguous or scope-excluded rows remain
fail-closed.

## Proof-Ready Technical Rows

The following 15 rows are documentation-proof-ready but not approved. They are
eligible only for an operator-fill proposal with placeholder reviewer metadata.

| row_id | surface | classification | official_evidence_refs |
|---|---|---|---|
| `public_rest_availability` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` refs `S2_JSON_RPC_TRANSPORTS`, `S5_REST_ORDER_BOOK` |
| `prod_testnet_ws_endpoint` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` refs `S1_ENVIRONMENTS`, `S2_JSON_RPC_TRANSPORTS` |
| `prod_testnet_rest_endpoint` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` refs `S1_ENVIRONMENTS`, `S2_JSON_RPC_TRANSPORTS` |
| `rest_snapshot_requirement` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` refs `S4_NOTIFICATIONS_RELIABILITY`, `S5_REST_ORDER_BOOK` |
| `gap_resubscribe_rule` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` ref `S4_NOTIFICATIONS_RELIABILITY` |
| `heartbeat_liveness_proof` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` ref `S6_HEARTBEAT` |
| `public_rate_subscription_limits` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` ref `S7_RATE_LIMITS` |
| `public_trades` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` ref `S8_TRADES_CHANNEL` |
| `ticker` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` ref `S9_TICKER_CHANNEL` |
| `mark_index_funding_open_interest` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` ref `S9_TICKER_CHANNEL` |
| `testnet_prod_difference` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` refs `S1_ENVIRONMENTS`, `S2_JSON_RPC_TRANSPORTS` |
| `first_message_snapshot` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` refs `S3_BOOK_CHANNEL`, `S4_NOTIFICATIONS_RELIABILITY` |
| `incremental_delta` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` ref `S3_BOOK_CHANNEL` |
| `prev_change_id` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` refs `S3_BOOK_CHANNEL`, `S4_NOTIFICATIONS_RELIABILITY` |
| `continuity_condition` | `claim_review` | `PROOF_READY_NOT_APPROVED` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` refs `S3_BOOK_CHANNEL`, `S4_NOTIFICATIONS_RELIABILITY` |

## Documentation-Only Legal Row

| row_id | surface | classification | official_evidence_refs | proposal_eligible |
|---|---|---|---|---|
| `regional_legal_access` | `claim_review` | `DOCUMENTATION_PROOF_READY` | `DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence` ref `S10_RESTRICTED_JURISDICTIONS` | `NO_LEGAL_APPROVAL` |

`regional_legal_access` is not classified as `PROOF_READY_NOT_APPROVED`
because legal access cannot be approved by documentation capture alone.

## Rows Kept Fail-Closed

| row_id | surface | classification | reason |
|---|---|---|---|
| `checksum_decision` | `claim_review` | `WAIT_INSUFFICIENT` | Scope-excluded from Phase 26AE and no current official checksum evidence is cited here. |
| `staleness_budget` | `claim_review` | `WAIT_POLICY` | Requires operator budget decision. |
| `receive_lag_budget` | `claim_review` | `WAIT_POLICY` | Requires operator budget decision. |
| `regional_legal_access_review` | `policy_review` | `WAIT_LEGAL` | Requires human legal review. |
| `separate_connector_enablement` | `policy_review` | `WAIT_POLICY` | Deferred to a separate explicit connector phase. |

## Counts

| category | count |
|---|---:|
| `PROOF_READY_NOT_APPROVED` | 15 |
| `DOCUMENTATION_PROOF_READY` | 1 |
| `WAIT_INSUFFICIENT` guardrail rows | 1 |
| `WAIT_POLICY` guardrail rows | 3 |
| `WAIT_LEGAL` guardrail rows | 1 |

No worksheet row is approved by this batch.
