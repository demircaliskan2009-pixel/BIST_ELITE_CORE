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
| `checksum_decision` | `deribit` | `PENDING` | `PENDING_MANUAL_REVIEW` | `PENDING` | `PENDING` | `DERIBIT_NOTIFICATIONS` | `checksum_decision` | `YES` | `NO` | `YES` | `PENDING` | `operational_policy:checksum_decision_missing` | `LEAVES_BLOCKER` |
| `liveness_policy` | `deribit` | `PENDING` | `PENDING_POLICY_BUDGET` | `PENDING` | `PENDING` | `DERIBIT_ENVIRONMENT` | `heartbeat_liveness_proof` | `YES` | `NO` | `YES` | `PENDING` | `operational_policy:liveness_policy_missing` | `LEAVES_BLOCKER` |
| `staleness_budget` | `deribit` | `PENDING` | `ENGINEERING_POLICY_PROPOSAL_PENDING_APPROVAL` | `PENDING` | `PENDING` | `DERIBIT_NOTIFICATIONS` | `staleness_budget` | `YES` | `NO` | `YES` | `PENDING` | `operational_policy:staleness_budget_missing` | `LEAVES_BLOCKER` |
| `receive_lag_budget` | `deribit` | `PENDING` | `ENGINEERING_POLICY_PROPOSAL_PENDING_APPROVAL` | `PENDING` | `PENDING` | `DERIBIT_NOTIFICATIONS` | `receive_lag_budget` | `YES` | `NO` | `YES` | `PENDING` | `operational_policy:receive_lag_budget_missing` | `LEAVES_BLOCKER` |
| `testnet_prod_review` | `deribit` | `PENDING` | `PENDING_MANUAL_REVIEW` | `PENDING` | `PENDING` | `DERIBIT_ENVIRONMENT` | `testnet_prod_difference` | `YES` | `NO` | `YES` | `PENDING` | `operational_policy:testnet_prod_review_missing` | `LEAVES_BLOCKER` |
| `regional_legal_access_review` | `deribit` | `PENDING` | `MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED` | `PENDING` | `PENDING` | `DERIBIT_RESTRICTED` | `regional_legal_access` | `NO` | `YES` | `YES` | `PENDING` | `operational_policy:regional_legal_access_review_missing` | `LEAVES_BLOCKER` |
| `separate_connector_enablement` | `deribit` | `PENDING` | `REQUIRED_SEPARATE_PHASE` | `PENDING` | `PENDING` | `DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST` | `connector_ready_dialects_expected` | `YES` | `NO` | `YES` | `PENDING` | `operational_policy:separate_connector_enablement_required` | `LEAVES_BLOCKER` |

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
