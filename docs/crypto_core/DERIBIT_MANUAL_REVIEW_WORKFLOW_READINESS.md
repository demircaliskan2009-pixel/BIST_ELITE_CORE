# Deribit Manual Review Workflow Readiness

Status: review workflow only / manual reviewer preparation / no readiness promotion.

This document inventories the exact manual approval surfaces that still block Deribit B1-B5. It is advisory workflow evidence only and does not change runtime behavior.

## A. EXECUTIVE STATUS

phase: 24C
document_type: MANUAL_REVIEW_WORKFLOW_READINESS
status: REVIEW_WORKFLOW_ONLY
operational_status: BLOCKED
operational_evidence_ready: false
connector_ready_dialects_expected: []
static_registry_verified: false
paper_shadow_integration_ready: false
live_trading_ready: false
private_api: FORBIDDEN
credentials: FORBIDDEN
orders: FORBIDDEN
agent_can_approve_b1_b5: NO
technical_connector_registry_ready: connector_ready_dialects_is_static_registry_only
operational_connector_authorization_requires: independent_human_origin_provenance
same_pr_ai_created_connector_approval_artifact: INSUFFICIENT
required_human_provenance_evidence: docs/crypto_core/DERIBIT_INDEPENDENT_HUMAN_CONNECTOR_APPROVAL_PROVENANCE.md

## B. CLOSED ADVISORY PROOFS

B8: CLOSED_BY_PROXY_AND_MAIN_CI_PUBLIC_SMOKE_PROOF
B10: CLOSED_WORKFLOW_REGISTERED_ON_MAIN
phase23d_run_id: 25658030184
phase23l_run_id: 25671516104
phase23l_classification: MAIN_ISOLATED_DERIBIT_SMOKE_ACCEPTED
advisory_readiness_effect: DOES_NOT_CLOSE_B1_B5
strictly_advisory_evidence_only: phase23d_ci_smoke, phase23l_main_smoke, phase23f_smoke_proof_record, phase24a_operator_approval_packet, phase24c_manual_review_workflow

Phase 23L smoke proof closes only the B8 and B10 advisory proof context. It does not close B1-B5 and does not change Deribit operational readiness.

## C. B1-B5 REVIEW MAP

source_snapshot_rows_pending: DERIBIT_NOTIFICATIONS, DERIBIT_ENVIRONMENT, DERIBIT_RATE_LIMITS, DERIBIT_INSTRUMENTS, DERIBIT_TICKER, DERIBIT_RESTRICTED
claim_review_rows_pending: public_websocket_availability, public_rest_availability, prod_testnet_ws_endpoint, prod_testnet_rest_endpoint, unauthenticated_public_market_data, orderbook_channel_feed, first_message_snapshot, incremental_delta, change_id, prev_change_id, continuity_condition, gap_resubscribe_rule, rest_snapshot_requirement, checksum_decision, heartbeat_liveness_proof, public_rate_subscription_limits, public_trades, ticker, mark_index_funding_open_interest, staleness_budget, receive_lag_budget, testnet_prod_difference, regional_legal_access
policy_rows_pending: checksum_decision, liveness_policy, staleness_budget, receive_lag_budget, testnet_prod_review, regional_legal_access_review, separate_connector_enablement
rows_requiring_reviewer_id: all source_snapshot_rows_pending, all claim_review_rows_pending, all policy_rows_pending
rows_requiring_reviewed_at_iso: all source_snapshot_rows_pending, all claim_review_rows_pending, all policy_rows_pending
rows_requiring_approval_scope: all B1-B5 decision records
rows_requiring_evidence_refs: all B1-B5 decision records
rows_requiring_source_hash_refs: all source_snapshot_rows_pending, all claim_review_rows_pending
rows_requiring_rejection_reasons_if_rejected: all manual decision rows
rows_requiring_human_operator_review: all source_snapshot_rows_pending, all claim_review_rows_pending, all policy_rows_pending, B1, B2, B3, B4, B5
rows_requiring_engineering_verification_after_human_approval: B4 static registry verification, B5 connector-ready dialect enablement phase

| blocker_id | worksheet_rows | current_status | controlling_docs | controlling_source_modules | controlling_tests | human_reviewer_required | agent_approval_allowed | approval_metadata_required | evidence_required | decision_values_allowed | current_default_decision | readiness_effect_now | must_remain_blocked_now |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B1 | checklist.operational_status | operational_status BLOCKED | docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md, docs/crypto_core/DERIBIT_B1_B5_OPERATOR_APPROVAL_PACKET.md, docs/crypto_core/DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md | src/crypto_core/venue/operational_evidence_readiness.py, src/crypto_core/venue/public_connector_readiness_report.py | tests/crypto_core/venue/test_phase22p_operational_evidence_acceptance.py, tests/crypto_core/venue/test_phase22u_public_connector_readiness_report.py, tests/crypto_core/venue/test_phase24a_deribit_b1_b5_operator_approval_packet.py | YES | NO | reviewer_id, reviewed_at_iso, decision, approval_scope, evidence_refs | explicit human blocker decision after B2, B3, and B4 approvals are recorded and reviewed | APPROVE / REJECT / DEFER | DEFER | NONE | YES |
| B2 | DERIBIT_NOTIFICATIONS, DERIBIT_ENVIRONMENT, DERIBIT_RATE_LIMITS, DERIBIT_INSTRUMENTS, DERIBIT_TICKER, DERIBIT_RESTRICTED; public_websocket_availability, public_rest_availability, prod_testnet_ws_endpoint, prod_testnet_rest_endpoint, unauthenticated_public_market_data, orderbook_channel_feed, first_message_snapshot, incremental_delta, change_id, prev_change_id, continuity_condition, gap_resubscribe_rule, rest_snapshot_requirement, checksum_decision, heartbeat_liveness_proof, public_rate_subscription_limits, public_trades, ticker, mark_index_funding_open_interest, staleness_budget, receive_lag_budget, testnet_prod_difference, regional_legal_access | phase22n_claim_review_validation_status BLOCKED_PENDING_MANUAL_APPROVAL | docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md, docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md, docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md, docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md | src/crypto_core/venue/official_source_snapshots.py, src/crypto_core/venue/official_claim_reviews.py, src/crypto_core/venue/operational_evidence_readiness.py | tests/crypto_core/venue/test_phase22n_official_claim_reviews.py, tests/crypto_core/venue/test_phase22p_operational_evidence_acceptance.py | YES | NO | reviewer_id, reviewed_at_iso, decision, approval_scope, evidence_refs, source_hash_refs | approved source snapshot metadata with content_sha256, approved claim rows with source_sha256, and explicit human approval notes | APPROVE / REJECT / DEFER | DEFER | NONE | YES |
| B3 | checksum_decision, liveness_policy, staleness_budget, receive_lag_budget, testnet_prod_review, regional_legal_access_review, separate_connector_enablement | phase22p_operational_acceptance_status BLOCKED_PENDING_POLICY_APPROVALS | docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md, docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md | src/crypto_core/venue/operational_evidence_readiness.py, src/crypto_core/venue/public_connector_enablement.py | tests/crypto_core/venue/test_phase22p_operational_evidence_acceptance.py, tests/crypto_core/venue/test_phase22r_deribit_operational_policy_review_worksheet.py, tests/crypto_core/venue/test_phase22s_public_connector_enablement.py | YES | NO | reviewer_id, reviewed_at_iso, decision, approval_scope, evidence_refs | approved policy rows for checksum_decision, liveness_policy, staleness_budget, receive_lag_budget, testnet_prod_review, regional_legal_access_review, and documented defer or reject rationale when not approved | APPROVE / REJECT / DEFER | DEFER | NONE | YES |
| B4 | checklist.static_registry_verified and public_feed_dialects.deribit:l2_orderbook:placeholder.enabled_for_connector | static_registry_verified false | docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md, docs/crypto_core/DERIBIT_B1_B5_OPERATOR_APPROVAL_PACKET.md, docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md | src/crypto_core/venue/public_feed_dialects.py, src/crypto_core/venue/public_connector_enablement.py, src/crypto_core/venue/public_connector_readiness_report.py | tests/crypto_core/venue/test_phase22s_public_connector_enablement.py, tests/crypto_core/venue/test_phase22u_public_connector_readiness_report.py, tests/crypto_core/venue/test_phase24a_deribit_b1_b5_operator_approval_packet.py | YES | NO | reviewer_id, reviewed_at_iso, decision, approval_scope, evidence_refs | explicit human engineering verification record confirming static registry review after B2 and B3 evidence acceptance is complete | APPROVE / REJECT / DEFER | DEFER | NONE | YES |
| B5 | separate_connector_enablement, phase22s_public_connector_enablement_status, phase22u_public_connector_readiness_report_status, connector_ready_dialects_expected | connector_ready_dialects empty | docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md, docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md, docs/crypto_core/DERIBIT_B1_B5_OPERATOR_APPROVAL_PACKET.md | src/crypto_core/venue/public_connector_enablement.py, src/crypto_core/venue/public_connector_readiness_report.py, src/crypto_core/venue/public_feed_dialects.py | tests/crypto_core/venue/test_phase22s_public_connector_enablement.py, tests/crypto_core/venue/test_phase22u_public_connector_readiness_report.py, tests/crypto_core/venue/test_phase24a_deribit_b1_b5_operator_approval_packet.py | YES | NO | reviewer_id, reviewed_at_iso, decision, approval_scope, evidence_refs | explicit separate PUBLIC_MARKET_DATA_ONLY connector enablement approval after B1, B2, B3, and B4 are cleared | APPROVE / REJECT / DEFER | DEFER | NONE | YES |

## D. REQUIRED HUMAN DECISION ORDER

1. Source snapshot manual review
2. Claim review manual review
3. Operational policy review
4. Operational evidence acceptance review
5. Static registry verification review
6. Separate public connector enablement review
7. Connector-ready dialect enablement phase
8. Paper/shadow integration phase
9. Private/live/order authorization phase

## E. MANUAL REVIEW METADATA CONTRACT

reviewer_id: REQUIRED
reviewed_at_iso: REQUIRED
decision: REQUIRED
approval_scope: REQUIRED
evidence_refs: REQUIRED
source_hash_refs: REQUIRED_WHEN_APPLICABLE
rejection_reasons: REQUIRED_IF_REJECTED
defer_reasons: REQUIRED_IF_DEFERRED
live_trading_authorization: FORBIDDEN
private_api_authorization: FORBIDDEN
order_authorization: FORBIDDEN

APPROVE: permitted only when the reviewer records all required metadata, attaches evidence_refs, records source_hash_refs when applicable, and keeps the approval scope within public market data review only.
REJECT: permitted only when rejection_reasons is populated with matching reject code(s) and supporting evidence_refs.
DEFER: the current fail-closed default for every unresolved row; defer_reasons is required and readiness_effect_now remains NONE.

## F. REJECTION / DEFER CODES

blocker_codes: b1:operational_status_blocked, b2:source_snapshot_review_pending, b2:claim_review_pending, b3:policy_approval_pending, b4:static_registry_unverified, b5:connector_ready_dialects_empty
policy_codes: policy:checksum_pending, policy:liveness_pending, policy:staleness_budget_pending, policy:receive_lag_budget_pending, policy:testnet_prod_pending, policy:regional_legal_pending
connector_codes: connector:separate_enablement_required
safety_codes: safety:private_api_forbidden, safety:orders_forbidden, safety:live_trading_forbidden
review_codes: review:metadata_missing, review:evidence_refs_missing, review:defer_requires_reason

## G. NON-PROMOTION ASSERTIONS

this document does not approve B1-B5.
this document does not change operational_status.
this document does not mark operational_evidence_ready true.
this document does not mark static_registry_verified true.
this document does not enable connector_ready_dialects.
this document does not authorize paper-shadow integration.
this document does not authorize private API.
this document does not authorize orders.
this document does not authorize live trading.
this document does not treat connector_ready_dialects() as operational approval.
this document requires independent human-origin connector approval provenance before B5 can be READY.

## H. NEXT HUMAN ACTION

Human reviewer must inspect source snapshot manifest, claim worksheet, and operational policy worksheet.
Human reviewer may choose APPROVE / REJECT / DEFER per row.
Until explicit valid approvals exist, all B1-B5 remain blocked.