# Deribit Next Blocker Summary - Phase 26U

status: NEXT_ACTION_PLAN_ONLY
supersedes: DERIBIT_NEXT_BLOCKER_SUMMARY_26Q.md

Phases 26R–26S dispatched and classified a minimal Deribit public smoke retry
(`duration_seconds=10`, `max_messages=10`, `sample_limit=10`). The run
(`26038507233`) concluded with `success` and `accepted=true`, capturing 9
events from `book.BTC-PERPETUAL.none.10.100ms`. This resolves the transient
timeout pattern recorded in Phase 26P: the two prior timeouts (runs
`26033502712` and `26035089720`, both 30s/100/100) were timing or runner
state artefacts, not a persistent network block.

However, all 9 captured events return `payload_sample.prev_change_id=null` and
`payload_sample.type=null`. The four remaining open raw-sequence claims
(`prev_change_id`, `continuity_condition`, `first_message_snapshot`,
`incremental_delta`) require non-null values for these fields. The
`book.BTC-PERPETUAL.none.10.100ms` subscription does not emit them. All open
claims remain WAIT_INSUFFICIENT. No new rows are approved. `pending_rows=26`.

## Capture Outcome Summary

| run_id | phase | dispatched_at_utc | head_sha | duration_s | max_msg | conclusion | message_count | rejection_reason |
|---|---|---|---|---|---|---|---|---|
| `26033502712` | 26I/26J | `2026-05-18T12:28:58Z` | `30aa40d9` | `30` | `100` | `failure` | `0` | `deribit_ws:timeout` |
| `26035089720` | 26N | `2026-05-18T13:00:24Z` | `de838f0e` | `30` | `100` | `failure` | `0` | `deribit_ws:timeout` |
| `26038507233` | 26R | `2026-05-18T14:04:03Z` | `6884356b` | `10` | `10` | `success` | `9` | _(none)_ |

## Approved Rows So Far

| row_id | surface | approval_scope | reviewer_id | reviewed_at_iso | evidence |
|---|---|---|---|---|---|
| `public_websocket_availability` | claim_review | `Phase25I_APPROVE_NOW_CANDIDATES_ONLY` | `demir_operator` | `2026-05-11T00:00:00Z` | `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` |
| `unauthenticated_public_market_data` | claim_review | `Phase25I_APPROVE_NOW_CANDIDATES_ONLY` | `demir_operator` | `2026-05-11T00:00:00Z` | `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` |
| `orderbook_channel_feed` | claim_review | `Phase25I_APPROVE_NOW_CANDIDATES_ONLY` | `demir_operator` | `2026-05-11T00:00:00Z` | `DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` |
| `change_id` | claim_review | `Phase25R_CHANGE_ID_ONLY` | `demir_operator` | `2026-05-11T00:00:00Z` | `DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`; `DERIBIT_PROOF_ARTIFACT_BATCH_25N.md`; `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` row `change_id` |

## Proof-Ready But Not Approved Rows

| row_id | status | reason |
|---|---|---|
| none | NO_PROPOSAL | Phase 26S artifact accepted but all remaining open claims require `prev_change_id` (non-null) or `type` (non-null), neither of which is emitted by `book.BTC-PERPETUAL.none.10.100ms`. |

## Rows Still Needing Raw Sequence Artifact

| row_id | exact_next_capture_requirement |
|---|---|
| `prev_change_id` | Accepted public smoke artifact with `message_count >= 1` and at least one observed event where `payload_sample.prev_change_id` is a non-null integer. Requires a channel subscription that emits `prev_change_id` (e.g. `book.BTC-PERPETUAL.100ms` or `book.BTC-PERPETUAL.raw`). |
| `continuity_condition` | Accepted artifact with adjacent observed events proving `current.payload_sample.prev_change_id == prior.payload_sample.change_id`. Requires the same non-null `prev_change_id` channel. |
| `first_message_snapshot` | Accepted artifact whose first observed book event proves snapshot semantics via a non-null `payload_sample.type`. Requires a channel subscription that emits `type`. |
| `incremental_delta` | Accepted artifact with a later observed event proving change or delta semantics via a non-null `payload_sample.type`. Requires the same `type`-emitting channel. |

## Channel Limitation Blockers

| blocker | details | required_action |
|---|---|---|
| `book.BTC-PERPETUAL.none.10.100ms` does not emit `prev_change_id` | All 9 events in Phase 26S return `prev_change_id=null`. This is a channel format limitation, not a connection failure. | Operator must identify and authorize a channel subscription that emits non-null `prev_change_id`. |
| `book.BTC-PERPETUAL.none.10.100ms` does not emit `type` | All 9 events return `type=null`. Snapshot vs incremental delta cannot be distinguished from this channel. | Operator must identify and authorize a channel subscription that emits a non-null `type` discriminator. |
| No channel change without operator authorization | The current harness uses `book.BTC-PERPETUAL.none.10.100ms` as the default channel. Changing it requires operator review and explicit authorization of the new channel name. | Operator must review Deribit API documentation for the correct full book channel format and authorize the change. |

## Next Exact Actions

| priority | action |
|---|---|
| 1 | Operator: review Deribit public WebSocket documentation to identify the channel subscription format that emits non-null `prev_change_id` and `type` fields (e.g. `book.BTC-PERPETUAL.100ms` or `book.BTC-PERPETUAL.raw`). |
| 2 | Operator: authorize changing the default channel in the smoke harness to the identified subscription format. |
| 3 | After authorization: update `DERIBIT_DEFAULT_PUBLIC_CHANNEL` in `src/crypto_core/data/deribit_public_ws_harness.py` to the authorized channel and re-run the smoke workflow. |
| 4 | Do NOT classify any raw sequence claim until `accepted=true`, `rejection_reasons=[]`, `message_count >= 1`, and the required fields are non-null in `sample_events`. |
| 5 | Do NOT modify the worksheet, connector enablement, or validator until all B1-B5 blockers are resolved. |

## Rows Needing Other Public Artifacts

| row_id | required_artifact |
|---|---|
| `gap_resubscribe_rule` | Committed official Deribit documentation excerpt proving gap recovery and resubscribe rule. |
| `heartbeat_liveness_proof` | Committed official Deribit documentation excerpt or environment proof for heartbeat, ping-pong, or liveness semantics. |
