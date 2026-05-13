# Deribit AI Assisted Review Proposal

Status: proposal only / not approval / non-mutating.

This file is proposal only. It is not approval and must not be written back
into the final worksheets automatically. It does not change B1-B5, does not
change validator outputs, does not enable any connector, and does not mutate
the three final human-review worksheets.

No source file changes are required.

Human must fill the final operator decision block manually after independent
review of the committed evidence package.

## Current Validator State

- accepted=false
- evidence_review_complete=false
- ready_for_engineering_patch=false
- connector_enablement_ready=false
- pending_rows=36
- connector_ready_dialects=0
- b1_b5_status={"B1": "BLOCKED", "B2": "BLOCKED", "B3": "BLOCKED", "B4": "BLOCKED", "B5": "BLOCKED"}

## Proposal Labels

- PROPOSE_APPROVE: committed evidence appears sufficient for a human to
  consider later approval, but no approval is recorded here.
- PROPOSE_REJECT: committed evidence appears inconsistent or insufficient for
  the row as written.
- PROPOSE_DEFER: keep the row blocked pending later phase review or deeper
  human source inspection.
- NEEDS_EXTERNAL_LEGAL_REVIEW: jurisdiction or legal access determination is
  required before any final row decision.
- NEEDS_OPERATOR_POLICY_DECISION: a human operator must choose a policy or
  threshold; any CANDIDATE_POLICY_VALUE below is advisory only.

## 36-Row Proposed Review Table

| surface | row_id | source_id if available | current_status | AI_proposed_decision | confidence | evidence_refs | required_human_action | blocker |
|---|---|---|---|---|---|---|---|---|
| source_snapshot | DERIBIT_NOTIFICATIONS | DERIBIT_NOTIFICATIONS | SUPPLIED_HASHED_PENDING_REVIEW | PROPOSE_APPROVE | MEDIUM | DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md Source Snapshots row DERIBIT_NOTIFICATIONS; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md Phase 22L | Verify official URL, retrieval timestamp, SHA256, and temp-file provenance against the terminal retrieval record before any human worksheet decision. | B2 |
| source_snapshot | DERIBIT_ENVIRONMENT | DERIBIT_ENVIRONMENT | SUPPLIED_HASHED_PENDING_REVIEW | PROPOSE_APPROVE | MEDIUM | DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md Source Snapshots row DERIBIT_ENVIRONMENT; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md Phase 22L | Verify official URL, retrieval timestamp, SHA256, and temp-file provenance against the terminal retrieval record before any human worksheet decision. | B2 |
| source_snapshot | DERIBIT_RATE_LIMITS | DERIBIT_RATE_LIMITS | SUPPLIED_HASHED_PENDING_REVIEW | PROPOSE_APPROVE | MEDIUM | DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md Source Snapshots row DERIBIT_RATE_LIMITS; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md Phase 22L | Verify official URL, retrieval timestamp, SHA256, and temp-file provenance against the terminal retrieval record before any human worksheet decision. | B2 |
| source_snapshot | DERIBIT_INSTRUMENTS | DERIBIT_INSTRUMENTS | SUPPLIED_HASHED_PENDING_REVIEW | PROPOSE_APPROVE | MEDIUM | DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md Source Snapshots row DERIBIT_INSTRUMENTS; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md Phase 22L | Verify official URL, retrieval timestamp, SHA256, and temp-file provenance against the terminal retrieval record before any human worksheet decision. | B2 |
| source_snapshot | DERIBIT_TICKER | DERIBIT_TICKER | SUPPLIED_HASHED_PENDING_REVIEW | PROPOSE_APPROVE | MEDIUM | DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md Source Snapshots row DERIBIT_TICKER; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md Phase 22L | Verify official URL, retrieval timestamp, SHA256, and temp-file provenance against the terminal retrieval record before any human worksheet decision. | B2 |
| source_snapshot | DERIBIT_RESTRICTED | DERIBIT_RESTRICTED | SUPPLIED_HASHED_PENDING_REVIEW | PROPOSE_APPROVE | MEDIUM | DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md Source Snapshots row DERIBIT_RESTRICTED; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md Phase 22L | Verify official URL, retrieval timestamp, SHA256, and temp-file provenance against the terminal retrieval record before any human worksheet decision. | B2 |
| claim_review | public_websocket_availability | DERIBIT_ENVIRONMENT | PENDING | PROPOSE_APPROVE | HIGH | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row public_websocket_availability; DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md Phase 23L smoke accepted true; DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md row DERIBIT_ENVIRONMENT | Confirm the hashed WebSocket documentation and the public smoke proof align on public WebSocket availability and keep scope PUBLIC_MARKET_DATA_ONLY. | B2 |
| claim_review | public_rest_availability | DERIBIT_INSTRUMENTS | PENDING | PROPOSE_APPROVE | MEDIUM | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row public_rest_availability; DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md row DERIBIT_INSTRUMENTS | Human must verify that the hashed public get_instruments documentation clearly supports unauthenticated public REST availability. | B2 |
| claim_review | prod_testnet_ws_endpoint | DERIBIT_ENVIRONMENT | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row prod_testnet_ws_endpoint; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md testnet_prod_semantic_equivalence UNKNOWN | Human must inspect the hashed environment documentation for exact production and testnet endpoint wording before any final worksheet decision. | B2 |
| claim_review | prod_testnet_rest_endpoint | DERIBIT_INSTRUMENTS | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row prod_testnet_rest_endpoint; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md testnet_prod_semantic_equivalence UNKNOWN | Human must inspect the hashed public REST documentation for exact production and testnet endpoint wording before any final worksheet decision. | B2 |
| claim_review | unauthenticated_public_market_data | DERIBIT_ENVIRONMENT | PENDING | PROPOSE_APPROVE | HIGH | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row unauthenticated_public_market_data; DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md PUBLIC_MARKET_DATA_ONLY scope; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md no credentials/private API | Confirm the hashed docs and smoke proof both support unauthenticated public market-data access only. | B2 |
| claim_review | orderbook_channel_feed | DERIBIT_NOTIFICATIONS | PENDING | PROPOSE_APPROVE | HIGH | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row orderbook_channel_feed; DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md channel book.BTC-PERPETUAL.none.10.100ms; DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md row DERIBIT_NOTIFICATIONS | Confirm the hashed notifications documentation matches the observed public order-book subscription shape used in the smoke proof. | B2 |
| claim_review | first_message_snapshot | DERIBIT_NOTIFICATIONS | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row first_message_snapshot; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md snapshot_delta_resync_proof_reviewed PENDING | Human must read the hashed notification examples and determine whether the first message is a snapshot. | B2 |
| claim_review | incremental_delta | DERIBIT_NOTIFICATIONS | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row incremental_delta; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md snapshot_delta_resync_proof_reviewed PENDING | Human must read the hashed notification examples and determine the exact delta semantics. | B2 |
| claim_review | change_id | DERIBIT_NOTIFICATIONS | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row change_id; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md sequence_change_id_prev_change_id_proof_reviewed PENDING | Human must verify exact change_id semantics from the hashed notification material. | B2 |
| claim_review | prev_change_id | DERIBIT_NOTIFICATIONS | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row prev_change_id; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md sequence_change_id_prev_change_id_proof_reviewed PENDING | Human must verify exact prev_change_id semantics from the hashed notification material. | B2 |
| claim_review | continuity_condition | DERIBIT_NOTIFICATIONS | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row continuity_condition; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md sequence_change_id_prev_change_id_proof_reviewed PENDING | Human must derive and record the continuity rule from the hashed notification documentation. | B2 |
| claim_review | gap_resubscribe_rule | DERIBIT_NOTIFICATIONS | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row gap_resubscribe_rule; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md snapshot_delta_resync_proof_reviewed PENDING | Human must determine the fail-closed gap handling or resubscribe rule from the hashed notification documentation. | B2 |
| claim_review | rest_snapshot_requirement | DERIBIT_NOTIFICATIONS | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row rest_snapshot_requirement; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md snapshot_delta_resync_proof_reviewed PENDING | Human must decide whether REST snapshot recovery is required, forbidden, or undocumented in the hashed evidence. | B2 |
| claim_review | checksum_decision | DERIBIT_NOTIFICATIONS | PENDING | NEEDS_OPERATOR_POLICY_DECISION | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row checksum_decision; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md checksum_absence_status UNKNOWN_OR_NOT_DOCUMENTED_IN_REVIEWED_OFFICIAL_SOURCES; DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md row checksum_decision | Human must choose the matching policy row only as CANDIDATE_POLICY_VALUE: FAIL_CLOSED_UNTIL_OFFICIAL_CHECKSUM_PROOF_OR_EXPLICIT_ABSENCE_REVIEW. | B2/B3 |
| claim_review | heartbeat_liveness_proof | DERIBIT_ENVIRONMENT | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row heartbeat_liveness_proof; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md heartbeat_ping_pong_liveness_status UNKNOWN_BLOCKED | Human must inspect the hashed WebSocket environment material for explicit heartbeat, ping-pong, or equivalent liveness proof. | B2 |
| claim_review | public_rate_subscription_limits | DERIBIT_RATE_LIMITS | PENDING | PROPOSE_DEFER | MEDIUM | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row public_rate_subscription_limits; DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md row DERIBIT_RATE_LIMITS; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md rate_subscription_limit_proof_reviewed PENDING | Human must inspect the hashed rate-limits section and extract the documented public subscription limits before any final worksheet decision. | B2 |
| claim_review | public_trades | DERIBIT_NOTIFICATIONS | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row public_trades; DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md row DERIBIT_NOTIFICATIONS | Human must inspect the hashed notification material to confirm whether a public trades feed and its semantics are explicitly documented. | B2 |
| claim_review | ticker | DERIBIT_TICKER | PENDING | PROPOSE_APPROVE | MEDIUM | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row ticker; DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md row DERIBIT_TICKER | Human must verify that the hashed ticker documentation supports the ticker availability and semantics claimed in the worksheet. | B2 |
| claim_review | mark_index_funding_open_interest | DERIBIT_TICKER | PENDING | PROPOSE_APPROVE | MEDIUM | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row mark_index_funding_open_interest; DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md row DERIBIT_TICKER | Human must verify that the hashed ticker documentation supports mark, index, funding, and open-interest fields as claimed. | B2 |
| claim_review | staleness_budget | DERIBIT_NOTIFICATIONS | PENDING | NEEDS_OPERATOR_POLICY_DECISION | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row staleness_budget; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md staleness_budget_status UNSATISFIED; DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md row staleness_budget | Human must define the matching policy row only as CANDIDATE_POLICY_VALUE: HUMAN_DEFINED_NUMERIC_STALENESS_BOUND_REQUIRED; no approved numeric bound exists in the current evidence package. | B2/B3 |
| claim_review | receive_lag_budget | DERIBIT_NOTIFICATIONS | PENDING | NEEDS_OPERATOR_POLICY_DECISION | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row receive_lag_budget; DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md receive_lag_ms_max 176; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md receive_lag_budget_status UNSATISFIED; DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md row receive_lag_budget | Human must define the matching policy row only as CANDIDATE_POLICY_VALUE: HUMAN_DEFINED_NUMERIC_RECEIVE_LAG_BOUND_REQUIRED; 176 ms from smoke proof is advisory evidence only, not approval. | B2/B3 |
| claim_review | testnet_prod_difference | DERIBIT_ENVIRONMENT | PENDING | PROPOSE_DEFER | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row testnet_prod_difference; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md testnet_prod_semantic_equivalence UNKNOWN | Human must document concrete production versus testnet differences from the hashed environment documentation before any final worksheet decision. | B2 |
| claim_review | regional_legal_access | DERIBIT_RESTRICTED | PENDING | NEEDS_EXTERNAL_LEGAL_REVIEW | LOW | DERIBIT_CLAIM_REVIEW_WORKSHEET.md row regional_legal_access; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md regional_legal_access_status MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED; DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md row regional_legal_access_review | Human must obtain external legal review for jurisdiction-specific access, including Turkey, before any final worksheet decision. | B2/B3 |
| policy_review | checksum_decision | DERIBIT_NOTIFICATIONS | PENDING | NEEDS_OPERATOR_POLICY_DECISION | LOW | DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md row checksum_decision; DERIBIT_CLAIM_REVIEW_WORKSHEET.md row checksum_decision; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md checksum_absence_status UNKNOWN_OR_NOT_DOCUMENTED_IN_REVIEWED_OFFICIAL_SOURCES | Human must record only CANDIDATE_POLICY_VALUE: FAIL_CLOSED_UNTIL_OFFICIAL_CHECKSUM_PROOF_OR_EXPLICIT_ABSENCE_REVIEW; do not treat this as approved policy in this file. | B3 |
| policy_review | liveness_policy | DERIBIT_ENVIRONMENT | PENDING | NEEDS_OPERATOR_POLICY_DECISION | LOW | DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md row liveness_policy; DERIBIT_CLAIM_REVIEW_WORKSHEET.md row heartbeat_liveness_proof; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md heartbeat_ping_pong_liveness_status UNKNOWN_BLOCKED | Human must record only CANDIDATE_POLICY_VALUE: FAIL_CLOSED_UNTIL_HEARTBEAT_PING_PONG_OR_EQUIVALENT_LIVENESS_IS_EXPLICITLY_REVIEWED. | B3 |
| policy_review | staleness_budget | DERIBIT_NOTIFICATIONS | PENDING | NEEDS_OPERATOR_POLICY_DECISION | LOW | DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md row staleness_budget; DERIBIT_CLAIM_REVIEW_WORKSHEET.md row staleness_budget; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md staleness_budget_status UNSATISFIED | Human must record only CANDIDATE_POLICY_VALUE: HUMAN_DEFINED_NUMERIC_STALENESS_BOUND_REQUIRED; the current evidence package contains no approved numeric staleness bound. | B3 |
| policy_review | receive_lag_budget | DERIBIT_NOTIFICATIONS | PENDING | NEEDS_OPERATOR_POLICY_DECISION | LOW | DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md row receive_lag_budget; DERIBIT_CLAIM_REVIEW_WORKSHEET.md row receive_lag_budget; DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md receive_lag_ms_max 176 | Human must record only CANDIDATE_POLICY_VALUE: HUMAN_DEFINED_NUMERIC_RECEIVE_LAG_BOUND_REQUIRED; 176 ms from the smoke proof is advisory evidence only. | B3 |
| policy_review | testnet_prod_review | DERIBIT_ENVIRONMENT | PENDING | NEEDS_OPERATOR_POLICY_DECISION | LOW | DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md row testnet_prod_review; DERIBIT_CLAIM_REVIEW_WORKSHEET.md row testnet_prod_difference; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md testnet_prod_semantic_equivalence UNKNOWN | Human must decide whether the documented production versus testnet differences are acceptable before any final worksheet decision. | B3 |
| policy_review | regional_legal_access_review | DERIBIT_RESTRICTED | PENDING | NEEDS_EXTERNAL_LEGAL_REVIEW | LOW | DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md row regional_legal_access_review; DERIBIT_CLAIM_REVIEW_WORKSHEET.md row regional_legal_access; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md regional_legal_access_status MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED | Human must obtain external legal sign-off before any final worksheet decision for regional access. | B3 |
| policy_review | separate_connector_enablement | DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST | PENDING | PROPOSE_DEFER | HIGH | DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md row separate_connector_enablement; DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md Phase 22S blocked pending separate enablement; deribit_manual_review_readiness.py Phase 25F separation | Human must carry forward defer reason separate_connector_enablement_is_future_phase and leave connector enablement for the later explicit PUBLIC_MARKET_DATA_ONLY phase. | B5 |

## Operator Decision Block

Blank on purpose. Human must fill this block manually after reviewing the
evidence package and this proposal.

- Human final decision summary: ______________________
- Human evidence references to carry into final worksheets: ______________________
- Human legal sign-off notes, if any: ______________________
- Human policy values to record later, if any: ______________________
- Human rationale for any defer or reject outcome: ______________________

This block is intentionally blank and proposal-only.