# Deribit Next Blocker Summary - Phase 25Q

status: NEXT_ACTION_PLAN_ONLY

Phase 25M-25Q produced one newly proof-ready row (`change_id`) from actual
observed Deribit public book sample events. No worksheet row was edited or
approved.

Phase 25R update: `change_id` is now approved under
`Phase25R_CHANGE_ID_ONLY` with supplied operator metadata. All other rows in
this summary remain blocked as listed.

## Rows Now Approved

| row_id | surface | evidence | next_human_action |
|---|---|---|---|
| `change_id` | claim_review | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_PROOF_ARTIFACT_BATCH_25N.md`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `change_id` | Approved in Phase 25R only; no additional action for this row unless re-review is requested. |

## Rows Still Needing Actual Observed Artifact

| row_id | missing_observed_artifact |
|---|---|
| `prev_change_id` | Observed book sample with non-null `prev_change_id`. |
| `first_message_snapshot` | Observed first message proving snapshot semantics, or official proof that this aggregated channel is snapshotless. |
| `incremental_delta` | Observed message proving change/delta semantics, or official proof resolving `type=null` aggregated payload behavior. |
| `continuity_condition` | Adjacent observed pair proving `prev_change_id[n] == change_id[n-1]`. |
| `public_trades` | Public trades smoke or recorded fixture. |
| `ticker` | Public ticker smoke or recorded fixture. |
| `mark_index_funding_open_interest` | Public ticker artifact proving mark, index, funding, and open-interest fields. |

## Rows Still Needing Official Documentation Excerpt

| row_id | next_artifact |
|---|---|
| `public_rest_availability` | `DERIBIT_REST_ENDPOINT_SECTION_EXCERPT_PROOF.md`. |
| `prod_testnet_ws_endpoint` | `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md`. |
| `prod_testnet_rest_endpoint` | `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md`. |
| `gap_resubscribe_rule` | `DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md`. |
| `rest_snapshot_requirement` | `DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md`. |
| `heartbeat_liveness_proof` | `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md`. |
| `public_rate_subscription_limits` | `DERIBIT_RATE_LIMITS_SECTION_EXCERPT_PROOF.md`. |
| `testnet_prod_difference` | `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md`. |

## Rows Needing Policy Values

| row_id | next_human_action |
|---|---|
| `checksum_decision` | Operator must choose an explicit checksum policy. |
| `liveness_policy` | Operator must choose an explicit liveness policy after official heartbeat proof. |
| `staleness_budget` | Operator must approve a concrete staleness budget. |
| `receive_lag_budget` | Operator must approve a concrete receive-lag budget. |
| `testnet_prod_review` | Operator must approve production/testnet policy stance after excerpt proof. |

## Legal Rows

| row_id | next_human_action |
|---|---|
| `regional_legal_access` | External legal/access review required. |
| `regional_legal_access_review` | Manual legal policy review required. |

## Separate Connector Enablement

`separate_connector_enablement` remains deferred. No connector enablement,
registry mutation, paper/shadow integration, or `connector_ready_dialects()`
change is authorized by this batch.

## Exact Next Safe Actions

1. Do not re-approve `change_id`; Phase 25R is the final approval for that
   row unless a later operator prompt explicitly requests re-review.
2. Run another PUBLIC_MARKET_DATA_ONLY observed book smoke that captures
   non-null `prev_change_id` or an official explanation of the observed
   `prev_change_id=null` aggregated channel behavior.
3. Commit official section excerpts for notifications, environment, REST, and
   rate-limit claims.
4. Supply explicit policy values and legal review artifacts in later phases.
