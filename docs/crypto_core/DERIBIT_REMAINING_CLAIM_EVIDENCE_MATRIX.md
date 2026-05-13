# Deribit Remaining Claim Evidence Matrix

- `status`: `ANALYSIS_ONLY`
- `phase`: `25J`
- `generated_at`: `2026-05-13`
- `baseline_commit`: `0e4558835bfce976aa0fc554283cf09940ded26a`
- `baseline_phase`: `Phase25I_merged`

## Safety Statement

This document is:

- **NOT** an approval of any worksheet row
- **NOT** a mutation of `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` or any other worksheet
- **NOT** a closure of any B1–B5 gate
- **NOT** an enablement of `connector_ready_dialects()`
- **NOT** a change to `evidence_review_complete`, `accepted`, or `connector_enablement_ready`
- **NOT** a modification of `public_feed_dialects.py` or the static registry
- **NOT** an authorization for paper trading, shadow trading, or live trading

All 20 remaining claim rows continue to be `PENDING` in the real worksheet until
explicit operator-reviewed patch phases (analogous to Phase 25I) are executed with
committed proof artifacts for each row.

---

## Baseline Validator State

| field | value |
|---|---|
| `accepted` | `False` |
| `evidence_review_complete` | `False` |
| `ready_for_engineering_patch` | `False` |
| `connector_enablement_ready` | `False` |
| `pending_rows` | `27` (0 manifest + 20 claims + 7 policies) |
| `B1` | `BLOCKED` |
| `B2` | `BLOCKED` |
| `B3` | `BLOCKED` |
| `B4` | `BLOCKED` |
| `B5` | `BLOCKED` |
| `connector_ready_dialects()` | `()` |

---

## Already Approved Claim Rows (Phase 25I — excluded from this matrix)

| claim_id | approved_at | reviewer_id |
|---|---|---|
| `public_websocket_availability` | `2026-05-11T00:00:00Z` | `demir_operator` |
| `unauthenticated_public_market_data` | `2026-05-11T00:00:00Z` | `demir_operator` |
| `orderbook_channel_feed` | `2026-05-11T00:00:00Z` | `demir_operator` |

---

## Classification Summary

| classification | count | claim_ids |
|---|---|---|
| `APPROVE_READY_WITH_EXISTING_EVIDENCE` | `0` | — |
| `NEEDS_OFFICIAL_DOC_SECTION_PROOF` | `8` | `public_rest_availability`, `prod_testnet_ws_endpoint`, `prod_testnet_rest_endpoint`, `gap_resubscribe_rule`, `rest_snapshot_requirement`, `heartbeat_liveness_proof`, `public_rate_subscription_limits`, `testnet_prod_difference` |
| `NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF` | `8` | `first_message_snapshot`, `incremental_delta`, `change_id`, `prev_change_id`, `continuity_condition`, `public_trades`, `ticker`, `mark_index_funding_open_interest` |
| `NEEDS_POLICY_DECISION` | `3` | `checksum_decision`, `staleness_budget`, `receive_lag_budget` |
| `NEEDS_LEGAL_REVIEW` | `1` | `regional_legal_access` |
| **total** | **20** | |

---

## Evidence Matrix

| claim_id | classification | source_id | primary_missing_proof | future_proof_artifact |
|---|---|---|---|---|
| `public_rest_availability` | `NEEDS_OFFICIAL_DOC_SECTION_PROOF` | `DERIBIT_INSTRUMENTS` | No committed excerpt from `#public-get_instruments` confirming the REST endpoint is public and unauthenticated. Source hash proves retrieval only. | `DERIBIT_REST_ENDPOINT_SECTION_EXCERPT_PROOF.md` — committed section excerpt from official docs confirming `GET /api/v2/public/get_instruments` is unauthenticated, with URL, auth requirement, and field list. |
| `prod_testnet_ws_endpoint` | `NEEDS_OFFICIAL_DOC_SECTION_PROOF` | `DERIBIT_ENVIRONMENT` | No committed excerpt pinning testnet URL (`test.deribit.com`) vs production URL (`www.deribit.com`) WebSocket semantics. Checklist `testnet_prod_semantic_equivalence: UNKNOWN`. | `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md` — committed section excerpt from official docs confirming exact WS endpoint URLs for both environments and any known behavioral differences. |
| `prod_testnet_rest_endpoint` | `NEEDS_OFFICIAL_DOC_SECTION_PROOF` | `DERIBIT_INSTRUMENTS` | No committed excerpt pinning testnet vs production REST endpoint semantics. Same root cause as `prod_testnet_ws_endpoint`. | `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md` — same artifact as above; covers REST endpoint URLs. |
| `first_message_snapshot` | `NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF` | `DERIBIT_NOTIFICATIONS` | Existing smoke captured 19 book messages but the committed proof record does not include a `type == snapshot` assertion on the first received message. No committed parser test verifies snapshot-first semantics. | `DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json` — committed harness artifact showing first message `type == snapshot`; or `test_phase25k_deribit_book_parse_sequence.py` parser unit test with a recorded message fixture. |
| `incremental_delta` | `NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF` | `DERIBIT_NOTIFICATIONS` | No committed artifact verifies that messages 2..N from the book channel have `type == change` with non-empty `bids`/`asks` change arrays. | `DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json` — committed artifact or parser test showing at least one delta message with non-empty change arrays after a snapshot. |
| `change_id` | `NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF` | `DERIBIT_NOTIFICATIONS` | Harness captures `sequence_id` per event but no committed artifact proves `change_id` is present, is an integer, and is monotonically increasing across consecutive messages. | `DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json` — committed artifact showing `change_id` values for N≥3 consecutive messages; or parser test asserting `change_id` is present and monotonically increasing. |
| `prev_change_id` | `NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF` | `DERIBIT_NOTIFICATIONS` | Harness captures `prev_sequence_id` per event but no committed artifact proves `prev_change_id` equals the previous message's `change_id`. | `DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json` — committed artifact or parser test asserting `prev_change_id[n] == change_id[n-1]` for N≥3 consecutive messages. |
| `continuity_condition` | `NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF` | `DERIBIT_NOTIFICATIONS` | No committed artifact or parser test verifies the full continuity condition: `prev_change_id[n] == change_id[n-1]` holds without gaps. Depends on `change_id` and `prev_change_id` proofs. | `DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json` — committed artifact or parser test demonstrating an unbroken `change_id` chain for N≥3 messages; gap-injection test confirming harness raises on discontinuity. |
| `gap_resubscribe_rule` | `NEEDS_OFFICIAL_DOC_SECTION_PROOF` | `DERIBIT_NOTIFICATIONS` | Official docs must state whether a gap in `change_id` requires resubscription or a REST snapshot fallback before harness recovery logic can be proven. No committed doc excerpt addresses gap recovery. | `DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md` — committed section excerpt from official docs describing gap recovery behavior; followed by `test_phase25k_deribit_book_parse_sequence.py` gap-injection test. |
| `rest_snapshot_requirement` | `NEEDS_OFFICIAL_DOC_SECTION_PROOF` | `DERIBIT_NOTIFICATIONS` | Official docs must state whether REST snapshot is required, optional, or prohibited during book recovery. No committed doc excerpt addresses REST-then-delta ordering. | `DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md` — committed section excerpt confirming REST snapshot recovery path (or lack thereof); followed by a harness or parser test for the REST→delta state machine. |
| `checksum_decision` | `NEEDS_POLICY_DECISION` | `DERIBIT_NOTIFICATIONS` | Deribit book notifications may include a checksum field. Operator must decide: fail-closed on checksum mismatch, skip, or validate. No approved policy value in `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md`. Checklist `checksum_absence_status: UNKNOWN_OR_NOT_DOCUMENTED_IN_REVIEWED_OFFICIAL_SOURCES`. | Operator approves `checksum_decision` row in `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md` with explicit policy value (e.g., `FAIL_CLOSED_ON_MISMATCH`); then harness is verified to enforce the approved policy. |
| `heartbeat_liveness_proof` | `NEEDS_OFFICIAL_DOC_SECTION_PROOF` | `DERIBIT_ENVIRONMENT` | No committed excerpt from official docs confirming heartbeat/ping-pong interval or liveness mechanism. Checklist `heartbeat_ping_pong_liveness_status: UNKNOWN_BLOCKED`. Harness does not currently enforce heartbeat timeout. Additionally, the operational policy worksheet contains a `liveness_policy` row with `claim_refs = heartbeat_liveness_proof`; the validator asserts `operational_policy:liveness_policy_missing` which keeps B3 BLOCKED. Both proof gates must be cleared to approve this row. | (1) `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md` — committed section excerpt confirming heartbeat/ping-pong semantics and interval; followed by harness liveness test and `test_phase25k_deribit_liveness.py`. (2) Operator approves `liveness_policy` row in `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md` with explicit liveness policy value before this claim can clear B3. |
| `public_rate_subscription_limits` | `NEEDS_OFFICIAL_DOC_SECTION_PROOF` | `DERIBIT_RATE_LIMITS` | Source hash for `DERIBIT_RATE_LIMITS` exists but no committed excerpt shows exact public WebSocket subscription rate limits. Checklist `rate_subscription_limit_proof_reviewed: PENDING`. | `DERIBIT_RATE_LIMITS_SECTION_EXCERPT_PROOF.md` — committed section excerpt from `#rate-limits` showing exact public subscription rate limits; or a committed harness constant referencing these limits with doc-hash justification. |
| `public_trades` | `NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF` | `DERIBIT_NOTIFICATIONS` | Harness allows `trades.*` channel pattern but no smoke was run on a trades channel. No committed artifact verifies trades feed field semantics (`instrument_name`, `price`, `amount`, `direction`). | `DERIBIT_TRADES_SMOKE_PROOF.json` — committed smoke artifact from `run_deribit_public_ws_smoke_test` with `trades.BTC-PERPETUAL.100ms` channel; or `test_phase25k_deribit_trades_channel.py` parser test with recorded fixture. |
| `ticker` | `NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF` | `DERIBIT_TICKER` | Source hash for `DERIBIT_TICKER` exists but no smoke was run on a ticker channel. No committed artifact verifies ticker field semantics. Harness allows `ticker.*` channel pattern. | `DERIBIT_TICKER_SMOKE_PROOF.json` — committed smoke artifact from `run_deribit_public_ws_smoke_test` with `ticker.BTC-PERPETUAL.100ms` channel; or `test_phase25k_deribit_ticker_channel.py` parser test with recorded fixture. |
| `mark_index_funding_open_interest` | `NEEDS_PUBLIC_SMOKE_OR_ARTIFACT_PROOF` | `DERIBIT_TICKER` | Source hash for `DERIBIT_TICKER` exists but no committed artifact proves `mark_price`, `index_price`, `current_funding`, and `open_interest` are present in ticker payload. Depends on ticker smoke proof. | `DERIBIT_TICKER_SMOKE_PROOF.json` — same as `ticker`; artifact must explicitly show `mark_price`, `index_price`, `current_funding`, and `open_interest` fields in a received ticker message. |
| `staleness_budget` | `NEEDS_POLICY_DECISION` | `DERIBIT_NOTIFICATIONS` | Advisory: smoke observed `receive_lag_ms_max: 176`. Operator must approve a concrete staleness budget (e.g., ≤500ms). No approved policy value in `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md`. Checklist `staleness_budget_status: UNSATISFIED`. | Operator approves `staleness_budget` row in `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md` with explicit value; then harness `max_receive_lag_ms` constant is aligned to approved value and tested. |
| `receive_lag_budget` | `NEEDS_POLICY_DECISION` | `DERIBIT_NOTIFICATIONS` | Advisory: smoke observed `receive_lag_ms_max: 176`. Operator must approve a concrete receive-lag budget. No approved policy value in `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md`. Checklist `staleness_budget_status: UNSATISFIED`. | Operator approves `receive_lag_budget` row in `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md` with explicit value; then harness enforces it at runtime. |
| `testnet_prod_difference` | `NEEDS_OFFICIAL_DOC_SECTION_PROOF` | `DERIBIT_ENVIRONMENT` | No committed excerpt confirms testnet vs production behavioral differences (message format, timing, field set). Checklist `testnet_prod_semantic_equivalence: UNKNOWN`. | `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md` — committed section excerpt from official docs comparing testnet and production environments; determines whether smoke must be run against testnet separately. |
| `regional_legal_access` | `NEEDS_LEGAL_REVIEW` | `DERIBIT_RESTRICTED` | Restricted-countries page source hash exists. Legal classification for Turkey and other relevant jurisdictions requires external legal review. Cannot be resolved from technical evidence alone. Checklist `regional_legal_access_status: MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED`. | External legal review artifact committed as `DERIBIT_LEGAL_ACCESS_REVIEW_RECORD.md`; approval of `regional_legal_access_review` row in `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md`. |

---

## Future Proof Artifact Index

| artifact_name | claim_ids | artifact_type |
|---|---|---|
| `DERIBIT_REST_ENDPOINT_SECTION_EXCERPT_PROOF.md` | `public_rest_availability` | `official_doc_excerpt` |
| `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md` | `prod_testnet_ws_endpoint`, `prod_testnet_rest_endpoint`, `heartbeat_liveness_proof`, `testnet_prod_difference` | `official_doc_excerpt` |
| `DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md` | `gap_resubscribe_rule`, `rest_snapshot_requirement` | `official_doc_excerpt` |
| `DERIBIT_RATE_LIMITS_SECTION_EXCERPT_PROOF.md` | `public_rate_subscription_limits` | `official_doc_excerpt` |
| `DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json` | `first_message_snapshot`, `incremental_delta`, `change_id`, `prev_change_id`, `continuity_condition` | `harness_parse_artifact` |
| `DERIBIT_TRADES_SMOKE_PROOF.json` | `public_trades` | `harness_smoke_artifact` |
| `DERIBIT_TICKER_SMOKE_PROOF.json` | `ticker`, `mark_index_funding_open_interest` | `harness_smoke_artifact` |
| `DERIBIT_LEGAL_ACCESS_REVIEW_RECORD.md` | `regional_legal_access` | `legal_review_record` |
| `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md` | `checksum_decision`, `staleness_budget`, `receive_lag_budget` | `operator_policy_decision` |
