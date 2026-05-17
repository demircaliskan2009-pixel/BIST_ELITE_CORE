# Deribit Claim Review Worksheet

Status: claim-level manual review worksheet / pending.

This worksheet maps each Deribit public-feed claim to the Phase 22L locally
hashed official documentation snapshot. It does not approve any claim, does not
verify operational readiness, and does not authorize a connector, registry
enablement, network client, private API, orders, or live execution.

All source URLs below were already listed in
`docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md` before Phase 22L.
The Phase 22L manifest is
`docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md`.

## Review Gate

- `worksheet_id`: `deribit-claim-review-worksheet-20260510`
- `venue_id`: `deribit`
- `operational_status`: `BLOCKED`
- `manual_review_required`: `YES`
- `manual_review_status`: `PENDING`
- `enabled_for_connector`: `false`
- `static_registry_verified`: `false`
- `connector_ready_dialects_expected`: `[]`
- `operational_readiness_effect`: `LEAVES_BLOCKER`
- `phase22n_claim_review_validation_gate`: `src/crypto_core/venue/official_claim_reviews.py`
- `phase22n_claim_review_validation_status`: `BLOCKED_PENDING_MANUAL_APPROVAL`

## Same Hash Caveat

All currently listed Deribit documentation fragment URLs resolved to the same
single-page documentation payload during Phase 22L terminal retrieval. The
shared `source_sha256` and byte size prove only that the documentation payload
was fetched and hashed. They do not prove claim-level approval, section-level
review, operational readiness, legal access, or connector safety.

## Claim Rows

| claim_id | source_id | official_url | source_sha256 | doc_section_or_anchor | claim_text_or_paraphrase | review_status | reviewer_id | reviewed_at_iso | decision | operational_readiness_effect | rejection_reason_if_pending |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `public_websocket_availability` | `DERIBIT_ENVIRONMENT` | `https://docs.deribit.com/#json-rpc-over-websocket` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#json-rpc-over-websocket` | Public WebSocket availability must be manually reviewed against the official docs payload. | `APPROVED` | `demir_operator` | `2026-05-11T00:00:00Z` | `APPROVED` | `LEAVES_BLOCKER` | `approved:Phase25I_APPROVE_NOW_CANDIDATES_ONLY source_hash:a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd smoke_proof:DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md` |
| `public_rest_availability` | `DERIBIT_INSTRUMENTS` | `https://docs.deribit.com/#public-get_instruments` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#public-get_instruments` | Public REST availability must be manually reviewed from official public method documentation. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:public_rest_availability_pending` |
| `prod_testnet_ws_endpoint` | `DERIBIT_ENVIRONMENT` | `https://docs.deribit.com/#json-rpc-over-websocket` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#json-rpc-over-websocket` | Production and testnet WebSocket endpoint claims require manual source review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:prod_testnet_ws_endpoint_pending` |
| `prod_testnet_rest_endpoint` | `DERIBIT_INSTRUMENTS` | `https://docs.deribit.com/#public-get_instruments` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#public-get_instruments` | Production and testnet REST endpoint claims require manual source review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:prod_testnet_rest_endpoint_pending` |
| `unauthenticated_public_market_data` | `DERIBIT_ENVIRONMENT` | `https://docs.deribit.com/#json-rpc-over-websocket` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#json-rpc-over-websocket` | Public market-data authentication requirements require manual review. | `APPROVED` | `demir_operator` | `2026-05-11T00:00:00Z` | `APPROVED` | `LEAVES_BLOCKER` | `approved:Phase25I_APPROVE_NOW_CANDIDATES_ONLY source_hash:a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd smoke_proof:DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md` |
| `orderbook_channel_feed` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | Orderbook channel or feed semantics require manual review. | `APPROVED` | `demir_operator` | `2026-05-11T00:00:00Z` | `APPROVED` | `LEAVES_BLOCKER` | `approved:Phase25I_APPROVE_NOW_CANDIDATES_ONLY source_hash:a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd smoke_proof:DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md` |
| `first_message_snapshot` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | First orderbook message snapshot behavior requires manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:first_message_snapshot_pending` |
| `incremental_delta` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | Incremental delta behavior requires manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:incremental_delta_pending` |
| `change_id` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | `change_id` field semantics require manual review. | `APPROVED` | `demir_operator` | `2026-05-11T00:00:00Z` | `APPROVED` | `LEAVES_BLOCKER` | `approved:Phase25R_CHANGE_ID_ONLY observed_proof:DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json classification:DERIBIT_PROOF_ARTIFACT_BATCH_25N.md` |
| `prev_change_id` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | `prev_change_id` field semantics require manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:prev_change_id_pending` |
| `continuity_condition` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | Sequence continuity conditions require manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:continuity_condition_pending` |
| `gap_resubscribe_rule` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | Gap handling and resubscribe or resync rules require manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:gap_resubscribe_rule_pending` |
| `rest_snapshot_requirement` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | REST snapshot requirement or non-requirement for book recovery requires manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:rest_snapshot_requirement_pending` |
| `checksum_decision` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | Checksum model presence, absence, or fail-closed handling requires manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:checksum_decision_pending` |
| `heartbeat_liveness_proof` | `DERIBIT_ENVIRONMENT` | `https://docs.deribit.com/#json-rpc-over-websocket` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#json-rpc-over-websocket` | Heartbeat, ping-pong, and liveness requirements require manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:heartbeat_liveness_proof_pending` |
| `public_rate_subscription_limits` | `DERIBIT_RATE_LIMITS` | `https://docs.deribit.com/#rate-limits` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#rate-limits` | Public rate and subscription limit requirements require manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:public_rate_subscription_limits_pending` |
| `public_trades` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | Public trades feed availability and semantics require manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:public_trades_pending` |
| `ticker` | `DERIBIT_TICKER` | `https://docs.deribit.com/#ticker-instrument_name-interval` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#ticker-instrument_name-interval` | Ticker field availability and semantics require manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:ticker_pending` |
| `mark_index_funding_open_interest` | `DERIBIT_TICKER` | `https://docs.deribit.com/#ticker-instrument_name-interval` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#ticker-instrument_name-interval` | Mark, index, funding, and open-interest data claims require manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:mark_index_funding_open_interest_pending` |
| `staleness_budget` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | Maximum staleness budget requires manual review and explicit budget definition. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:staleness_budget_pending` |
| `receive_lag_budget` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#notifications` | Maximum receive-lag budget requires manual review and explicit budget definition. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:receive_lag_budget_pending` |
| `testnet_prod_difference` | `DERIBIT_ENVIRONMENT` | `https://docs.deribit.com/#json-rpc-over-websocket` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#json-rpc-over-websocket` | Testnet and production semantic differences require manual review. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:testnet_prod_difference_pending` |
| `regional_legal_access` | `DERIBIT_RESTRICTED` | `https://docs.deribit.com/#restricted-countries` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` | `#restricted-countries` | Regional, legal, and access restrictions require manual review; no Turkey approval is recorded. | `PENDING` | `PENDING` | `PENDING` | `PENDING` | `LEAVES_BLOCKER` | `manual_review:regional_legal_access_pending` |

## Completion Rule

Every row remains pending until a human reviewer records reviewer metadata,
review time, a claim decision, and claim-specific evidence notes. Hash equality
across rows is expected for the current single-page documentation payload and
must not be used as a substitute for claim-level review. The Phase 22N
validation gate can validate only supplied manual review records; it cannot
auto-approve any current Deribit worksheet row.
