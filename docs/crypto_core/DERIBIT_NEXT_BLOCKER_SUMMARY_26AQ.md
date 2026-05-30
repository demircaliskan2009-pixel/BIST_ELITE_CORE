# Deribit Next Blocker Summary — Phase 26AQ

status: NEXT_BLOCKER_SUMMARY
phase: 26AQ
supersedes: DERIBIT_NEXT_BLOCKER_SUMMARY_26AL.md
reviewed_at_iso: 2026-05-19T00:00:00Z

## Validator State After Phase 26AM-26AN

```
accepted:                  False
evidence_review_complete:  False
ready_for_engineering_patch: False
connector_enablement_ready: False
pending_rows:              3
rejected_rows:             0
deferred_rows:             0
connector_ready_dialects:  0
```

## B1-B5 Status

| Gate | Status | Reason |
|------|--------|--------|
| B1 | BLOCKED | Gates on B2+B3+B4 — blocked while any child is blocked |
| B2 | BLOCKED | claim_review:regional_legal_access is PENDING |
| B3 | BLOCKED | policy_review:regional_legal_access_review and policy_review:separate_connector_enablement are PENDING |
| B4 | BLOCKED | static_registry_verified=false — engineering step after B2+B3 |
| B5 | BLOCKED | connector_ready_dialects empty — separate PUBLIC_MARKET_DATA_ONLY phase required |

## Approved in Phase 26AM-26AN (8 rows)

### Claim worksheet (3 rows)

| claim_id | policy_value |
|----------|-------------|
| `checksum_decision` | `NO_CHECKSUM_FIELD_APPROVED_FOR_CURRENT_PUBLIC_DATA_EVIDENCE` |
| `staleness_budget` | `MAX_STALENESS_MS_2000` |
| `receive_lag_budget` | `MAX_RECEIVE_LAG_MS_1000` |

### Policy worksheet (5 rows)

| policy_id | policy_value |
|-----------|-------------|
| `checksum_decision` | `NO_CHECKSUM_FIELD_APPROVED_FOR_CURRENT_PUBLIC_DATA_EVIDENCE` |
| `liveness_policy` | `PUBLIC_WS_LIVENESS_TIMEOUT_MS_10000` |
| `staleness_budget` | `MAX_STALENESS_MS_2000` |
| `receive_lag_budget` | `MAX_RECEIVE_LAG_MS_1000` |
| `testnet_prod_review` | `PROD_AND_TESTNET_MUST_REMAIN_EXPLICITLY_CONFIG_SEPARATED` |

## Cumulative Approved Totals

- Claim rows approved (total): 22  (19 from Phase 26AJ + 3 from Phase 26AN)
- Policy rows approved (total): 5  (0 prior + 5 from Phase 26AN)
- Source snapshot rows approved: 6 (unchanged)

## Remaining Pending Rows (3)

| row_id | worksheet | blocker_type | required_action |
|--------|-----------|-------------|-----------------|
| `regional_legal_access` | claim | LEGAL | External legal review for Turkey/regional access; no engineering path to unblock |
| `regional_legal_access_review` | policy | LEGAL | Legal review for regional access policy; NOT an engineering policy decision |
| `separate_connector_enablement` | policy | CONNECTOR_PHASE | Separate explicit PUBLIC_MARKET_DATA_ONLY connector-readiness phase required |

## Next Unblocking Steps

### A — Legal Review (blocks B2 + B3)

Action: Obtain formal legal review of `regional_legal_access` claim and
`regional_legal_access_review` policy row. No engineering substitution is
permitted. This is outside the scope of the operator's engineering approval.

- Required: External legal counsel review of Deribit restricted-countries policy
- Applicable row: `claim_review:regional_legal_access` and `policy_review:regional_legal_access_review`
- After: pending_rows → 1 (only `separate_connector_enablement` remains)
- After: B2 → READY, B3 → BLOCKED (separate_connector_enablement still pending)

### B — Connector Enablement Phase (blocks B3 + B5)

Action: Initiate a separate `PUBLIC_MARKET_DATA_ONLY` connector-enablement phase.
This phase is NOT part of the current evidence review. It requires:
  - Explicit operator authorization for `PUBLIC_MARKET_DATA_ONLY` run mode
  - Approval of `separate_connector_enablement` policy row
  - `public_feed_dialects.py` dialect entries (engineering step)
  - static_registry_verified=true gate (B4)
  - connector_ready_dialects() non-empty (B5)

Forbidden in this phase: no implicit fallback, no paper/shadow/live until
`separate_connector_enablement` is explicitly approved.

### C — Static Registry (B4)

After B2 and B3 are both READY: engineering step to set static_registry_verified=true
and update public_feed_dialects.py. Must not be done before legal and connector gates.

## What Was NOT Changed

- `public_feed_dialects.py` — unchanged, connector_ready_dialects() == 0
- `deribit_manual_review_readiness.py` — unchanged (read-only validator)
- `DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md` — unchanged
- `enabled_for_connector` header — false (unchanged)
- `static_registry_verified` header — false (unchanged)
- No paper / shadow / live integration
- No private API / credentials / orders

## Evidence References

- DERIBIT_POLICY_DECISION_AUDIT_26AM.md (this phase audit)
- DERIBIT_NEXT_BLOCKER_SUMMARY_26AL.md (prior summary)
- DERIBIT_OPERATOR_APPROVAL_EXECUTION_AUDIT_26AI.md
- DERIBIT_CLAIM_REVIEW_WORKSHEET.md (current state: 22/23 claim rows approved)
- DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md (current state: 5/7 policy rows approved)
