# Deribit Official Evidence Package Draft

Status: draft / DR_REPORTED official-source evidence intake.

This file records only the Deribit public order-book facts reported by the Deep
Research dossier for Phase 22J. The dossier is DR_REPORTED secondary evidence,
not primary evidence, and still needs local retrieval, reproducible hashes, and
manual review. This file is not a live connector authorization, does not enable
a static registry dialect, and must not be treated as a network, WebSocket, REST,
private API, credential, or order-submission implementation.

## Operational Verification Status

Operational connector readiness: **blocked**.

The official Deribit URLs below are DR_REPORTED research inputs for claim
mapping. The `CONTENT_HASH_UNAVAILABLE` values are manual hash placeholders.
They may be used by offline tests to prove overlay mechanics, but they are not
reproducible content hashes. They must be replaced by independently
reproducible content hashes and reviewer evidence before any operational
verification can pass.

`CONTENT_HASH_UNAVAILABLE`, missing hashes, missing retrieval timestamps,
summary-only Deep Research prose, and placeholder official-doc refs are all
fail-closed. Unknown operational fields remain blockers:

- public subscription rate limits beyond the cited official limit text
- max staleness
- max receive lag
- checksum semantics; absence of checksum proof is not operational proof
- testnet versus production differences
- regional, legal, and access review
- heartbeat, ping, and pong requirements unless official proof is added

`operational_status`: `BLOCKED`

`manual_review_required`: `YES`

`manual_hash_required`: `YES`

`enabled_for_connector`: `false`

`static_registry_verified`: `false`

Manual operational evidence review gate:
`docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md`.
This draft remains blocked until that checklist has official-source URLs,
positive retrieval timestamps, reproducible SHA256/content hashes, reviewer
metadata, manual approval, and all fail-closed operational budget reviews.

Phase 22K local official-source snapshot/hash intake contract:
`src/crypto_core/venue/official_source_snapshots.py`.
`official_source_snapshots_supplied`: `false`
`official_source_snapshot_hashes_validated`: `false`
This draft remains blocked until locally supplied source snapshots pass that
inert metadata/hash contract and manual review stays approved.

## Package Fields

- `package_id`: `deribit-public-book-phase22b-draft`
- `venue_id`: `deribit`
- `research_date`: `2026-05-09`
- `retrieved_at_ns`: `2200000000000`
- `retrieved_at_iso`: `2026-05-09T00:00:00Z`
- `source_count`: `6`
- `dossier_status`: `DR_REPORTED_NEEDS_LOCAL_RETRIEVAL`
- `reviewer_id`: `phase22b-draft-review`
- `verifier_id`: `phase22b-offline-overlay-test`
- `rejection_reasons`: `[]`

## Official Source Ids

- `DERIBIT_NOTIFICATIONS`
  - `source_id`: `DERIBIT_NOTIFICATIONS`
  - `venue`: `deribit`
  - `official_url`: `https://docs.deribit.com/#notifications`
  - `retrieval_date`: `2026-05-09`
  - `retrieved_at_iso`: `2026-05-09T00:00:00Z`
  - `retrieval_status`: `DR_REPORTED_NEEDS_LOCAL_RETRIEVAL`
  - `retrieved_at_ns`: `2200000000000`
  - `content_hash`: `CONTENT_HASH_UNAVAILABLE`
  - `manual_hash_required`: `YES`
  - `manual_review_required`: `YES`
  - `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `DERIBIT_ENVIRONMENT`
  - `source_id`: `DERIBIT_ENVIRONMENT`
  - `venue`: `deribit`
  - `official_url`: `https://docs.deribit.com/#json-rpc-over-websocket`
  - `retrieval_date`: `2026-05-09`
  - `retrieved_at_iso`: `2026-05-09T00:00:00Z`
  - `retrieval_status`: `DR_REPORTED_NEEDS_LOCAL_RETRIEVAL`
  - `retrieved_at_ns`: `2200000000000`
  - `content_hash`: `CONTENT_HASH_UNAVAILABLE`
  - `manual_hash_required`: `YES`
  - `manual_review_required`: `YES`
  - `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `DERIBIT_RATE_LIMITS`
  - `source_id`: `DERIBIT_RATE_LIMITS`
  - `venue`: `deribit`
  - `official_url`: `https://docs.deribit.com/#rate-limits`
  - `retrieval_date`: `2026-05-09`
  - `retrieved_at_iso`: `2026-05-09T00:00:00Z`
  - `retrieval_status`: `DR_REPORTED_NEEDS_LOCAL_RETRIEVAL`
  - `retrieved_at_ns`: `2200000000000`
  - `content_hash`: `CONTENT_HASH_UNAVAILABLE`
  - `manual_hash_required`: `YES`
  - `manual_review_required`: `YES`
  - `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `DERIBIT_INSTRUMENTS`
  - `source_id`: `DERIBIT_INSTRUMENTS`
  - `venue`: `deribit`
  - `official_url`: `https://docs.deribit.com/#public-get_instruments`
  - `retrieval_date`: `2026-05-09`
  - `retrieved_at_iso`: `2026-05-09T00:00:00Z`
  - `retrieval_status`: `DR_REPORTED_NEEDS_LOCAL_RETRIEVAL`
  - `retrieved_at_ns`: `2200000000000`
  - `content_hash`: `CONTENT_HASH_UNAVAILABLE`
  - `manual_hash_required`: `YES`
  - `manual_review_required`: `YES`
  - `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `DERIBIT_TICKER`
  - `source_id`: `DERIBIT_TICKER`
  - `venue`: `deribit`
  - `official_url`: `https://docs.deribit.com/#ticker-instrument_name-interval`
  - `retrieval_date`: `2026-05-09`
  - `retrieved_at_iso`: `2026-05-09T00:00:00Z`
  - `retrieval_status`: `DR_REPORTED_NEEDS_LOCAL_RETRIEVAL`
  - `retrieved_at_ns`: `2200000000000`
  - `content_hash`: `CONTENT_HASH_UNAVAILABLE`
  - `manual_hash_required`: `YES`
  - `manual_review_required`: `YES`
  - `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `DERIBIT_RESTRICTED`
  - `source_id`: `DERIBIT_RESTRICTED`
  - `venue`: `deribit`
  - `official_url`: `https://docs.deribit.com/#restricted-countries`
  - `retrieval_date`: `2026-05-09`
  - `retrieved_at_iso`: `2026-05-09T00:00:00Z`
  - `retrieval_status`: `DR_REPORTED_NEEDS_LOCAL_RETRIEVAL`
  - `retrieved_at_ns`: `2200000000000`
  - `content_hash`: `CONTENT_HASH_UNAVAILABLE`
  - `manual_hash_required`: `YES`
  - `manual_review_required`: `YES`
  - `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`

## Evidence Items

Each item below requires a real official source URL, content hash, and retrieval
timestamp before it can be promoted outside offline tests.

### Item 1: Initial Book Notification Snapshot

- `evidence_id`: `deribit:l2_orderbook:placeholder::initial-book-snapshot`
- `source_id`: `DERIBIT_NOTIFICATIONS`
- `doc_url`: `https://docs.deribit.com/#notifications`
- `source_name`: `DERIBIT_NOTIFICATIONS`
- `doc_type`: `l2_orderbook`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE:DERIBIT_NOTIFICATIONS:initial-book-snapshot`
- `retrieved_at_ns`: `2200000000001`
- `retrieval_date`: `2026-05-09`
- `manual_hash_required`: `YES`
- `cited_claim_text`: First public WebSocket book notification is a snapshot.
- `official_source_citation`: supplied Phase 22B Deribit research fact 1.
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `rejection_reasons`: `[]`

### Item 2: Subsequent Book Notifications Are Deltas

- `evidence_id`: `deribit:l2_orderbook:placeholder::subsequent-book-deltas`
- `source_id`: `DERIBIT_NOTIFICATIONS`
- `doc_url`: `https://docs.deribit.com/#notifications`
- `source_name`: `DERIBIT_NOTIFICATIONS`
- `doc_type`: `l2_orderbook`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE:DERIBIT_NOTIFICATIONS:subsequent-book-deltas`
- `retrieved_at_ns`: `2200000000002`
- `retrieval_date`: `2026-05-09`
- `manual_hash_required`: `YES`
- `cited_claim_text`: Subsequent public book notifications are incremental deltas.
- `official_source_citation`: supplied Phase 22B Deribit research fact 2.
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `rejection_reasons`: `[]`

### Item 3: Change Id Continuity

- `evidence_id`: `deribit:l2_orderbook:placeholder::change-id-continuity`
- `source_id`: `DERIBIT_NOTIFICATIONS`
- `doc_url`: `https://docs.deribit.com/#notifications`
- `source_name`: `DERIBIT_NOTIFICATIONS`
- `doc_type`: `l2_orderbook`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE:DERIBIT_NOTIFICATIONS:change-id-continuity`
- `retrieved_at_ns`: `2200000000003`
- `retrieval_date`: `2026-05-09`
- `manual_hash_required`: `YES`
- `cited_claim_text`: Book deltas carry `change_id` and `prev_change_id` continuity.
- `official_source_citation`: supplied Phase 22B Deribit research fact 3.
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `rejection_reasons`: `[]`

### Item 4: Prev Change Id Mismatch Requires Resync

- `evidence_id`: `deribit:l2_orderbook:placeholder::prev-change-id-resync`
- `source_id`: `DERIBIT_NOTIFICATIONS`
- `doc_url`: `https://docs.deribit.com/#notifications`
- `source_name`: `DERIBIT_NOTIFICATIONS`
- `doc_type`: `l2_orderbook`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE:DERIBIT_NOTIFICATIONS:prev-change-id-resync`
- `retrieved_at_ns`: `2200000000004`
- `retrieval_date`: `2026-05-09`
- `manual_hash_required`: `YES`
- `cited_claim_text`: `prev_change_id` mismatch requires resubscribe or resync.
- `official_source_citation`: supplied Phase 22B Deribit research fact 4.
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `rejection_reasons`: `[]`

### Item 5: Zero Gap Tolerance

- `evidence_id`: `deribit:l2_orderbook:placeholder::max-gap-tolerance-zero`
- `source_id`: `DERIBIT_NOTIFICATIONS`
- `doc_url`: `https://docs.deribit.com/#notifications`
- `source_name`: `DERIBIT_NOTIFICATIONS`
- `doc_type`: `l2_orderbook`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE:DERIBIT_NOTIFICATIONS:max-gap-tolerance-zero`
- `retrieved_at_ns`: `2200000000005`
- `retrieval_date`: `2026-05-09`
- `manual_hash_required`: `YES`
- `cited_claim_text`: `max_gap_tolerance` is zero for the offline Deribit L2 continuity model.
- `official_source_citation`: supplied Phase 22B Deribit research fact 5.
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `rejection_reasons`: `[]`

### Item 6: Public Market Data Unauthenticated

- `evidence_id`: `deribit:l2_orderbook:placeholder::public-market-data-unauthenticated`
- `source_id`: `DERIBIT_ENVIRONMENT`
- `doc_url`: `https://docs.deribit.com/#json-rpc-over-websocket`
- `source_name`: `DERIBIT_ENVIRONMENT`
- `doc_type`: `l2_orderbook`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE:DERIBIT_ENVIRONMENT:public-market-data-unauthenticated`
- `retrieved_at_ns`: `2200000000006`
- `retrieval_date`: `2026-05-09`
- `manual_hash_required`: `YES`
- `cited_claim_text`: Public market data subscriptions do not require private credentials.
- `official_source_citation`: supplied Phase 22D Deribit research mapping.
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `rejection_reasons`: `[]`

### Item 7: Production And Testnet WS Endpoints

- `evidence_id`: `deribit:l2_orderbook:placeholder::prod-testnet-ws-endpoints`
- `source_id`: `DERIBIT_ENVIRONMENT`
- `doc_url`: `https://docs.deribit.com/#json-rpc-over-websocket`
- `source_name`: `DERIBIT_ENVIRONMENT`
- `doc_type`: `l2_orderbook`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE:DERIBIT_ENVIRONMENT:prod-testnet-ws-endpoints`
- `retrieved_at_ns`: `2200000000007`
- `retrieval_date`: `2026-05-09`
- `manual_hash_required`: `YES`
- `cited_claim_text`: Production and testnet WebSocket environments are documented separately.
- `official_source_citation`: supplied Phase 22D Deribit research mapping.
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `rejection_reasons`: `[]`

### Item 8: Reconnect Requires Resubscribe Snapshot

- `evidence_id`: `deribit:l2_orderbook:placeholder::reconnect-resubscribe-snapshot`
- `source_id`: `DERIBIT_NOTIFICATIONS`
- `doc_url`: `https://docs.deribit.com/#notifications`
- `source_name`: `DERIBIT_NOTIFICATIONS`
- `doc_type`: `l2_orderbook`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE:DERIBIT_NOTIFICATIONS:reconnect-resubscribe-snapshot`
- `retrieved_at_ns`: `2200000000008`
- `retrieval_date`: `2026-05-09`
- `manual_hash_required`: `YES`
- `cited_claim_text`: Reconnect requires resubscribe and a fresh full snapshot for order-book recovery.
- `official_source_citation`: supplied Phase 22D Deribit research mapping.
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `rejection_reasons`: `[]`

### Item 9: Ticker Open Interest And Mark Price

- `evidence_id`: `deribit:l2_orderbook:placeholder::ticker-open-interest-mark-price`
- `source_id`: `DERIBIT_TICKER`
- `doc_url`: `https://docs.deribit.com/#ticker-instrument_name-interval`
- `source_name`: `DERIBIT_TICKER`
- `doc_type`: `l2_orderbook`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE:DERIBIT_TICKER:ticker-open-interest-mark-price`
- `retrieved_at_ns`: `2200000000009`
- `retrieval_date`: `2026-05-09`
- `manual_hash_required`: `YES`
- `cited_claim_text`: Ticker data includes open interest and mark price fields.
- `official_source_citation`: supplied Phase 22D Deribit research mapping.
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `rejection_reasons`: `[]`

### Item 10: Index And Funding Feeds

- `evidence_id`: `deribit:l2_orderbook:placeholder::index-funding-feeds`
- `source_id`: `DERIBIT_TICKER`
- `doc_url`: `https://docs.deribit.com/#ticker-instrument_name-interval`
- `source_name`: `DERIBIT_TICKER`
- `doc_type`: `l2_orderbook`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE:DERIBIT_TICKER:index-funding-feeds`
- `retrieved_at_ns`: `2200000000010`
- `retrieval_date`: `2026-05-09`
- `manual_hash_required`: `YES`
- `cited_claim_text`: Index and funding market-data feeds are documented public market-data surfaces.
- `official_source_citation`: supplied Phase 22D Deribit research mapping.
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `rejection_reasons`: `[]`

### Item 11: Public Subscribe Rate-Limit Evidence

- `evidence_id`: `deribit:l2_orderbook:placeholder::public-subscribe-rate-limit`
- `source_id`: `DERIBIT_RATE_LIMITS`
- `doc_url`: `https://docs.deribit.com/#rate-limits`
- `source_name`: `DERIBIT_RATE_LIMITS`
- `doc_type`: `l2_orderbook`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE:DERIBIT_RATE_LIMITS:public-subscribe-rate-limit`
- `retrieved_at_ns`: `2200000000011`
- `retrieval_date`: `2026-05-09`
- `manual_hash_required`: `YES`
- `cited_claim_text`: Public subscription rate-limit evidence exists, but budgets still require manual review before connector authorization.
- `official_source_citation`: supplied Phase 22D Deribit research mapping.
- `evidence_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `rejection_reasons`: `[]`

## Dialect Claim Mapping

- `supported_dialect_id`: `deribit:l2_orderbook:placeholder`
- `supported_feed_type`: `l2_orderbook`
- `deribit_dialect_verification`: `false`
- `dialect_verification_status`: `DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED`
- `enabled_for_connector`: `false`
- `connector_ready`: `false`
- `sequence_model_evidence`: `change_id` / `prev_change_id` continuity maps to `prev_final_range`.
- `checksum_model_evidence`: `UNKNOWN_OR_NOT_DOCUMENTED_IN_REVIEWED_OFFICIAL_SOURCES`
- `checksum_model`: `UNKNOWN_OR_NOT_DOCUMENTED_IN_REVIEWED_OFFICIAL_SOURCES`
- `legacy_checksum_blocker_label`: `NONE_OR_UNKNOWN_WITH_MANUAL_REVIEW`
- `heartbeat_ping_pong_evidence`: `UNKNOWN`
- `heartbeat_ping_pong_status`: `UNKNOWN_BLOCKED`
- `snapshot_delta_resync_evidence`: Initial notification is snapshot, subsequent notifications are deltas, and mismatch requires resubscribe or resync.
- `rate_limit_evidence`: `DR_REPORTED_NEEDS_LOCAL_RETRIEVAL_BUDGET_BLOCKED`
- `regional_legal_access_evidence`: `UNKNOWN`
- `regional_legal_access_status`: `MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED`
- `turkey_legal_access_evidence`: `UNKNOWN`
- `turkey_regional_access_status`: `MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED`
- `max_staleness_ns_evidence`: `UNKNOWN`
- `staleness_budget_status`: `UNSATISFIED`
- `max_receive_lag_ns_evidence`: `UNKNOWN`
- `receive_lag_budget_status`: `UNSATISFIED`
- `testnet_prod_semantic_equivalence`: `UNKNOWN`
- `testnet_prod_difference_status`: `BLOCKED_UNLESS_EXPLICIT_OFFICIAL_SOURCE_PROVES_EQUIVALENCE`

## Safety Warnings

- Do not include secrets.
- Do not include API keys.
- Do not include passphrases, tokens, private keys, or account identifiers.
- Do not convert this draft into static registry verification.
- Do not enable connector readiness globally from this draft.
- Do not treat placeholder URLs or placeholder hashes as operational evidence.
- Do not treat summary-only Deep Research text as verified official evidence.
- Unknown operational fields remain fail-closed until official source evidence is supplied.
