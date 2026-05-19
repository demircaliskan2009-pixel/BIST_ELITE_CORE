# Deribit Operational Policy Review Worksheet

Status: operational policy manual review worksheet / pending.

This worksheet records the manual operational policy decisions required before
the Phase 22P operational evidence acceptance gate can pass for Deribit public
data. It does not approve any policy, does not verify operational readiness,
and does not authorize a connector, registry enablement, network client,
private API, orders, or live execution.

## Review Gate

- `worksheet_id`: `deribit-operational-policy-review-worksheet-20260510`
- `venue_id`: `deribit`
- `operational_status`: `BLOCKED`
- `manual_review_required`: `YES`
- `manual_review_status`: `PENDING`
- `enabled_for_connector`: `false`
- `static_registry_verified`: `false`
- `connector_ready_dialects_expected`: `[]`
- `operational_readiness_effect`: `LEAVES_BLOCKER`
- `phase22p_operational_acceptance_gate`: `src/crypto_core/venue/operational_evidence_readiness.py`
- `phase22p_operational_acceptance_status`: `BLOCKED_PENDING_POLICY_APPROVALS`
- `phase22s_public_connector_enablement_gate`: `src/crypto_core/venue/public_connector_enablement.py`
- `phase22s_public_connector_enablement_status`: `BLOCKED_PENDING_SEPARATE_ENABLEMENT_APPROVAL`

## Policy Rows

| policy_id | venue_id | policy_status | policy_blocker_status | reviewer_id | reviewed_at_iso | source_refs | claim_refs | engineering_policy_required | legal_review_required | manual_approval_required | decision | rejection_reason_if_pending | operational_readiness_effect |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `checksum_decision` | `deribit` | `APPROVED` | `APPROVED_FAIL_CLOSED` | `demir_operator` | `2026-05-19T00:00:00Z` | `DERIBIT_NOTIFICATIONS` | `checksum_decision` | `YES` | `NO` | `YES` | `APPROVED` | `approved:Phase26AM_POLICY_DECISIONS_PUBLIC_DATA_ONLY policy_value:NO_CHECKSUM_FIELD_APPROVED_FOR_CURRENT_PUBLIC_DATA_EVIDENCE enforcement:FAIL_CLOSED_IF_SELECTED_CHANNEL_OR_DOCS_REQUIRE_CHECKSUM registry_effect:DO_NOT_SET_SUPPORTS_CHECKSUM_TRUE_IN_THIS_PHASE evidence_refs:DERIBIT_POLICY_DECISION_AUDIT_26AM.md` | `LEAVES_BLOCKER` |
| `liveness_policy` | `deribit` | `APPROVED` | `APPROVED_FAIL_CLOSED` | `demir_operator` | `2026-05-19T00:00:00Z` | `DERIBIT_ENVIRONMENT` | `heartbeat_liveness_proof` | `YES` | `NO` | `YES` | `APPROVED` | `approved:Phase26AM_POLICY_DECISIONS_PUBLIC_DATA_ONLY policy_value:PUBLIC_WS_LIVENESS_TIMEOUT_MS_10000 enforcement:FAIL_CLOSED_ON_NO_MESSAGE_OR_NO_HEARTBEAT_WITHIN_10000MS reconnect_action:RESUBSCRIBE_OR_RECONNECT_REQUIRED evidence_refs:DERIBIT_POLICY_DECISION_AUDIT_26AM.md` | `LEAVES_BLOCKER` |
| `staleness_budget` | `deribit` | `APPROVED` | `APPROVED_FAIL_CLOSED` | `demir_operator` | `2026-05-19T00:00:00Z` | `DERIBIT_NOTIFICATIONS` | `staleness_budget` | `YES` | `NO` | `YES` | `APPROVED` | `approved:Phase26AM_POLICY_DECISIONS_PUBLIC_DATA_ONLY policy_value:MAX_STALENESS_MS_2000 enforcement:MARK_FEED_STALE_AND_BLOCK_DOWNSTREAM_READINESS_IF_EXCEEDED evidence_refs:DERIBIT_POLICY_DECISION_AUDIT_26AM.md` | `LEAVES_BLOCKER` |
| `receive_lag_budget` | `deribit` | `APPROVED` | `APPROVED_FAIL_CLOSED` | `demir_operator` | `2026-05-19T00:00:00Z` | `DERIBIT_NOTIFICATIONS` | `receive_lag_budget` | `YES` | `NO` | `YES` | `APPROVED` | `approved:Phase26AM_POLICY_DECISIONS_PUBLIC_DATA_ONLY policy_value:MAX_RECEIVE_LAG_MS_1000 enforcement:REJECT_OR_QUARANTINE_EVENT_IF_EXCEEDED evidence_refs:DERIBIT_POLICY_DECISION_AUDIT_26AM.md` | `LEAVES_BLOCKER` |
| `testnet_prod_review` | `deribit` | `APPROVED` | `APPROVED_FAIL_CLOSED` | `demir_operator` | `2026-05-19T00:00:00Z` | `DERIBIT_ENVIRONMENT` | `testnet_prod_difference` | `YES` | `NO` | `YES` | `APPROVED` | `approved:Phase26AM_POLICY_DECISIONS_PUBLIC_DATA_ONLY policy_value:PROD_AND_TESTNET_MUST_REMAIN_EXPLICITLY_CONFIG_SEPARATED enforcement:NO_IMPLICIT_ENVIRONMENT_FALLBACK;PROD_DEFAULT_FOR_LIVE_FORBIDDEN_UNTIL_LATER_ENABLEMENT evidence_refs:DERIBIT_POLICY_DECISION_AUDIT_26AM.md` | `LEAVES_BLOCKER` |
| `regional_legal_access_review` | `deribit` | `APPROVED` | `APPROVED_OPERATOR_LEGAL_SIGNOFF` | `demir_operator` | `2026-05-19T00:00:00Z` | `DERIBIT_RESTRICTED` | `regional_legal_access` | `NO` | `YES` | `YES` | `APPROVE` | `approved:Phase26AV_TURKEY_PUBLIC_MARKET_DATA_ONLY_OPERATOR_LEGAL_SIGNOFF policy_value:TURKEY_PUBLIC_MARKET_DATA_ONLY_OPERATOR_SIGNOFF_NO_LOGIN_NO_PRIVATE_API_NO_ORDERS_NO_LIVE_NO_COMMERCIAL_REDISTRIBUTION_WITHOUT_DERIBIT_APPROVAL limitation:NO_EXPLICIT_PUBLIC_DATA_GEO_SAFE_HARBOR limitation:MARKET_DATA_PERSONAL_USE_ONLY_WITHOUT_PRIOR_WRITTEN_APPROVAL warning:NON_LEGAL_ADVICE_OPERATOR_GOVERNANCE_SIGNOFF_ONLY evidence_refs:DERIBIT_REGIONAL_LEGAL_ACCESS_RESEARCH_PACK_26AR.md;DERIBIT_REGIONAL_LEGAL_ACCESS_PROOF_BATCH_26AS.md;DERIBIT_OPERATOR_LEGAL_SIGNOFF_PROPOSAL_26AT.md;DERIBIT_OPERATOR_LEGAL_SIGNOFF_EXECUTION_AUDIT_26AV.md` | `LEAVES_BLOCKER` |
| `separate_connector_enablement` | `deribit` | `DEFERRED` | `REQUIRED_SEPARATE_PHASE` | `demir_operator` | `2026-05-19T00:00:00Z` | `DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST` | `connector_ready_dialects_expected` | `YES` | `NO` | `YES` | `DEFER` | `reason:SEPARATE_PUBLIC_MARKET_DATA_CONNECTOR_ENABLEMENT_PHASE_REQUIRED connector_enablement_ready:False enabled_for_connector:false static_registry_verified:false connector_ready_dialects_expected:[] no_approval_this_phase:True` | `LEAVES_BLOCKER` |

## Completion Rule

Every policy row remains pending until a human reviewer records reviewer
metadata, review time, and a policy decision. The separate connector enablement
row cannot be completed in this evidence phase; it requires a later explicitly
authorized connector-readiness phase. Until then, Deribit operational evidence
acceptance remains blocked and `connector_ready_dialects()` must remain empty.

Phase 22S records the separate public connector enablement gate, but it does
not approve the `separate_connector_enablement` row. Current Deribit connector
enablement remains pending, static registry verification remains false, and the
only permitted future run-mode approval would be an explicit
`PUBLIC_MARKET_DATA_ONLY` manual approval in a later phase.
