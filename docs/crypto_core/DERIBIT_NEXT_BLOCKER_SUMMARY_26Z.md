# Deribit Next Blocker Summary - Phase 26Z

status: NEXT_ACTION_PLAN_ONLY
supersedes: DERIBIT_NEXT_BLOCKER_SUMMARY_26U.md
NOT_an_approval: true
NOT_worksheet_mutation: true
NOT_connector_enablement: true

Phase 26V–26Z audited all repo-committed evidence for Deribit public book
channel subscription formats. No channel candidate is supported by committed
official documentation for capture. Phase 26W (channel-parametric capture)
was skipped because no class-A channel candidate exists. Phase 26X (artifact
classification) was skipped. Phase 26Y recorded the exact official excerpt
gaps. `pending_rows=26`. B1-B5 remain BLOCKED.

## Channel Audit Finding (Phase 26V)

| finding | detail |
|---|---|
| current_channel | `book.BTC-PERPETUAL.none.10.100ms` (aggregated) |
| phase_26s_result | `prev_change_id=null`, `type=null` for all 9 events |
| candidate_class_A | none — no channel supported by committed official doc |
| `book.BTC-PERPETUAL.100ms` | class B: needs official excerpt |
| `book.BTC-PERPETUAL.raw` | class C: forbidden (`"raw"` in harness `_FORBIDDEN_CHANNEL_TOKENS`) |
| 26W_capture_dispatched | false |
| 26X_artifact_classified | false |
| gap_doc | `DERIBIT_CHANNEL_OFFICIAL_EXCERPT_GAP_26Y.md` |

## Approved Rows So Far

| row_id | surface | approval_scope | reviewer_id | reviewed_at_iso | evidence |
|---|---|---|---|---|---|
| `public_websocket_availability` | claim_review | `Phase25I_APPROVE_NOW_CANDIDATES_ONLY` | `demir_operator` | `2026-05-11T00:00:00Z` | `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` |
| `unauthenticated_public_market_data` | claim_review | `Phase25I_APPROVE_NOW_CANDIDATES_ONLY` | `demir_operator` | `2026-05-11T00:00:00Z` | `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` |
| `orderbook_channel_feed` | claim_review | `Phase25I_APPROVE_NOW_CANDIDATES_ONLY` | `demir_operator` | `2026-05-11T00:00:00Z` | `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` |
| `change_id` | claim_review | `Phase25R_CHANGE_ID_ONLY` | `demir_operator` | `2026-05-11T00:00:00Z` | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_PROOF_ARTIFACT_BATCH_25N.md`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `change_id` |

## All Remaining Pending Blockers (26 rows)

All 26 rows remain pending as reported by `evaluate_deribit_manual_review_readiness()`.

### Raw-Sequence Artifact Blockers (4 rows)

These rows require an accepted smoke artifact from a channel that emits non-null
`prev_change_id` and `type`. No such channel has been identified from committed
repo evidence. The operator must first commit an official excerpt (see Phase 26Y
gap doc) before capture can proceed.

| row_id | exact_capture_requirement | channel_status |
|---|---|---|
| `claim_review:prev_change_id` | Accepted artifact with at least one event where `payload_sample.prev_change_id` is a non-null integer. | No authorized channel. Official excerpt gap: `BOOK_CHANNEL_FORMAT_VARIANTS`. |
| `claim_review:continuity_condition` | Accepted artifact with adjacent events proving `current.prev_change_id == prior.change_id`. | Depends on `prev_change_id` channel. Same gap. |
| `claim_review:first_message_snapshot` | Accepted artifact whose first book event has a non-null `payload_sample.type` proving snapshot semantics. | No authorized channel. Official excerpt gap: `BOOK_SNAPSHOT_DELTA_SEMANTICS`. |
| `claim_review:incremental_delta` | Accepted artifact with a later event having a non-null `payload_sample.type` proving delta semantics. | Depends on type-emitting channel. Same gap. |

### Documentation Artifact Blockers (15 rows)

| row_id | required_artifact |
|---|---|
| `claim_review:public_rest_availability` | Committed excerpt confirming Deribit public REST endpoints are available without authentication. |
| `claim_review:prod_testnet_ws_endpoint` | Committed excerpt confirming Deribit production and testnet WebSocket endpoint URLs. |
| `claim_review:prod_testnet_rest_endpoint` | Committed excerpt confirming Deribit production and testnet REST endpoint URLs. |
| `claim_review:rest_snapshot_requirement` | Committed documentation proving whether REST snapshot is required before WebSocket delta processing. Official excerpt gap: `BOOK_CONTINUITY_GAP_RECOVERY_RULE`. |
| `claim_review:checksum_decision` | Committed documentation or operator decision on Deribit order book checksum validation. Official excerpt gap: `BOOK_CHECKSUM_FIELD`. |
| `claim_review:gap_resubscribe_rule` | Committed official Deribit documentation excerpt proving gap recovery and resubscribe rule. Official excerpt gap: `BOOK_CONTINUITY_GAP_RECOVERY_RULE`. |
| `claim_review:heartbeat_liveness_proof` | Committed official Deribit documentation excerpt or environment proof for heartbeat/ping-pong/liveness semantics. |
| `claim_review:public_rate_subscription_limits` | Committed documentation confirming Deribit public WebSocket subscription rate limits. |
| `claim_review:public_trades` | Committed documentation or observation confirming public trades channel format and semantics. |
| `claim_review:ticker` | Committed documentation confirming Deribit ticker channel format and update frequency. |
| `claim_review:mark_index_funding_open_interest` | Committed documentation confirming mark price, index price, funding rate, and open interest channels. |
| `claim_review:staleness_budget` | Committed operator decision and documentation basis for maximum acceptable data staleness budget. |
| `claim_review:receive_lag_budget` | Committed operator decision and documentation basis for maximum acceptable receive lag budget. |
| `claim_review:testnet_prod_difference` | Committed documentation enumerating known differences between Deribit testnet and production environments. |
| `claim_review:regional_legal_access` | Committed legal review confirming the operating jurisdiction has no restriction on Deribit API access. |

### Policy Review Blockers (7 rows)

| row_id | required_action |
|---|---|
| `policy_review:checksum_decision` | Operator must decide whether to implement Deribit order book checksum validation (enabled or explicitly waived with justification). |
| `policy_review:liveness_policy` | Operator must define and commit the liveness detection and reconnection policy for Deribit WebSocket connections. |
| `policy_review:staleness_budget` | Operator must approve the maximum staleness budget for Deribit market data in the risk pipeline. |
| `policy_review:receive_lag_budget` | Operator must approve the maximum receive lag budget for Deribit WebSocket messages. |
| `policy_review:testnet_prod_review` | Operator must review and confirm testnet vs. production difference implications for the system. |
| `policy_review:regional_legal_access_review` | Operator must complete and document the regional legal access review for Deribit. |
| `policy_review:separate_connector_enablement` | Operator must separately authorize connector enablement after all B1-B5 blockers are resolved. |

## Channel Limitation Blockers (26V Finding)

| blocker | details | required_action |
|---|---|---|
| No class-A channel candidate | No repo-committed official excerpt identifies a channel that emits `prev_change_id` (non-null) or `type`. The current channel (`book.BTC-PERPETUAL.none.10.100ms`) does not emit these fields (Phase 26S finding). | Operator must commit official excerpt identifying the correct channel format before any new capture is authorized. |
| `book.BTC-PERPETUAL.raw` forbidden | `"raw"` is in `_FORBIDDEN_CHANNEL_TOKENS` in `deribit_public_ws_harness.py`. This is intentional security design. | If official docs identify `book.BTC-PERPETUAL.raw` as the correct channel, operator must explicitly authorize removing `"raw"` from forbidden tokens after security review. |
| `book.BTC-PERPETUAL.100ms` not matched by harness pattern | `_AGGREGATED_CHANNEL_PATTERNS` requires `.none.<group>.` in book channel format. | If official docs confirm `book.BTC-PERPETUAL.100ms` emits the required fields, operator must authorize adding a new pattern to `_AGGREGATED_CHANNEL_PATTERNS`. |

## Next Exact Actions

| priority | action |
|---|---|
| 1 | Operator reads `DERIBIT_NOTIFICATIONS` section on book channels. The page was fetched and hashed in Phase 22L — the hash is in `DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md`. |
| 2 | Operator commits exact excerpt from that section as a new file in `docs/crypto_core/official_sources/deribit/20260510/`. |
| 3 | Excerpt must identify: exact channel format string, which fields it emits (`prev_change_id`, `type`), snapshot/delta semantics, gap recovery rule. |
| 4 | Operator authorizes channel format addition to harness `_AGGREGATED_CHANNEL_PATTERNS` (or forbidden token removal if applicable) in a new patch. |
| 5 | After authorization: engineering adds the pattern, smoke is dispatched, artifact is classified per 26X path. |
| 6 | Do NOT modify the worksheet, connector enablement, or validator until all B1-B5 blockers are resolved. |
| 7 | Do NOT add any channel to the harness without explicit operator authorization backed by a committed official excerpt. |
