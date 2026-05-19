# Deribit Policy Decision Audit — Phase 26AM

status: POLICY_DECISION_AUDIT_ONLY
phase: 26AM
reviewer_id: demir_operator
reviewed_at_iso: 2026-05-19T00:00:00Z
approval_scope: Phase26AM_POLICY_DECISIONS_PUBLIC_DATA_ONLY
NOT_connector_enablement: true
NOT_static_registry_enablement: true
NOT_paper_shadow_live_integration: true
NOT_private_api_credentials_orders: true

## Purpose

This document pre-authorizes operator-approved fail-closed policy values for
the 8 non-legal, non-connector-enablement Deribit worksheet rows that remain
PENDING after Phase 26AJ. It is an audit record only. No connector, registry,
paper/shadow/live integration, or private API access is authorized at any
point in this document.

## Prior State

- main after PR #64 (Phase 26AI-26AL)
- pending_rows = 11
- claim rows approved = 19
- policy rows approved = 0

## Rows Authorized for APPROVE in This Phase

### Claim Worksheet (3 rows)

1. `checksum_decision` — claim_id in DERIBIT_CLAIM_REVIEW_WORKSHEET.md
2. `staleness_budget` — claim_id in DERIBIT_CLAIM_REVIEW_WORKSHEET.md
3. `receive_lag_budget` — claim_id in DERIBIT_CLAIM_REVIEW_WORKSHEET.md

### Policy Worksheet (5 rows)

4. `checksum_decision` — policy_id in DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md
5. `liveness_policy` — policy_id in DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md
6. `staleness_budget` — policy_id in DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md
7. `receive_lag_budget` — policy_id in DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md
8. `testnet_prod_review` — policy_id in DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md

**Total rows authorized: 8**

## Operator-Approved Policy Values

### 1. checksum_decision
- policy_value: `NO_CHECKSUM_FIELD_APPROVED_FOR_CURRENT_PUBLIC_DATA_EVIDENCE`
- enforcement: `FAIL_CLOSED_IF_SELECTED_CHANNEL_OR_DOCS_REQUIRE_CHECKSUM`
- registry_effect: `DO_NOT_SET_SUPPORTS_CHECKSUM_TRUE_IN_THIS_PHASE`
- rationale: Current public book channel documentation evidence does not
  confirm a checksum field. System must fail closed if any future channel or
  doc version introduces a checksum requirement.

### 2. liveness_policy
- policy_value: `PUBLIC_WS_LIVENESS_TIMEOUT_MS_10000`
- enforcement: `FAIL_CLOSED_ON_NO_MESSAGE_OR_NO_HEARTBEAT_WITHIN_10000MS`
- reconnect_action: `RESUBSCRIBE_OR_RECONNECT_REQUIRED`
- rationale: 10 000 ms liveness window is conservative for a 24/7 perpetual
  futures public feed. Heartbeat or any message resets the timer. No message
  or heartbeat within this window triggers fail-closed reconnect.

### 3. staleness_budget
- policy_value: `MAX_STALENESS_MS_2000`
- enforcement: `MARK_FEED_STALE_AND_BLOCK_DOWNSTREAM_READINESS_IF_EXCEEDED`
- rationale: 2 000 ms staleness budget is conservative and aligns with
  intraday data quality requirements for any downstream edge or risk engine.

### 4. receive_lag_budget
- policy_value: `MAX_RECEIVE_LAG_MS_1000`
- enforcement: `REJECT_OR_QUARANTINE_EVENT_IF_EXCEEDED`
- rationale: 1 000 ms receive-lag limit prevents stale events from entering
  the order book reconstruction pipeline. Events exceeding this threshold are
  quarantined and not used for downstream decisions.

### 5. testnet_prod_review
- policy_value: `PROD_AND_TESTNET_MUST_REMAIN_EXPLICITLY_CONFIG_SEPARATED`
- enforcement: `NO_IMPLICIT_ENVIRONMENT_FALLBACK; PROD_DEFAULT_FOR_LIVE_FORBIDDEN_UNTIL_LATER_ENABLEMENT`
- rationale: Production and testnet endpoints must never be resolved
  implicitly. Any live integration must have an explicit environment
  configuration gate. This policy is separate from and prior to any connector
  enablement.

## Rows Forbidden / Must Remain Blocked

The following 3 rows are NOT authorized in this phase:

| row_id | worksheet | reason |
|---|---|---|
| `regional_legal_access` | claim | Legal/regulatory review required; no Turkey legal approval on record |
| `regional_legal_access_review` | policy | Legal review required; NOT an engineering policy decision |
| `separate_connector_enablement` | policy | Separate explicit connector-readiness phase required; NOT enabled here |

## Expected Validator State After Patch

- pending_rows: 3
  - `claim_review:regional_legal_access`
  - `policy_review:regional_legal_access_review`
  - `policy_review:separate_connector_enablement`
- accepted: False
- evidence_review_complete: False (pending_rows > 0)
- ready_for_engineering_patch: False
- connector_enablement_ready: False
- B1: BLOCKED
- B2: BLOCKED (claim_review:regional_legal_access pending)
- B3: BLOCKED (policy_review rows pending)
- B4: BLOCKED (static_registry_verified=false)
- B5: BLOCKED (connector_ready_dialects empty)
- connector_ready_dialects(): 0

## Evidence References

- DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md
- DERIBIT_OFFICIAL_DOCS_PROOF_BATCH_26AF.md
- DERIBIT_PROOF_ARTIFACT_BATCH_26AG.md
- DERIBIT_OPERATOR_FILL_PROPOSAL_26AH.md
- DERIBIT_NEXT_BLOCKER_SUMMARY_26AH.md
- DERIBIT_OPERATOR_APPROVAL_EXECUTION_AUDIT_26AI.md
- DERIBIT_NEXT_BLOCKER_SUMMARY_26AL.md

## Audit Verdict

CONSISTENT — 8 rows authorized for APPROVE. 3 rows explicitly forbidden.
No connector enablement. No static registry enablement. No paper/shadow/live.
