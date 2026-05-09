# Deribit Official Evidence Package Draft

Status: draft / supplied evidence intake.

This file records only the Deribit public order-book facts supplied for Phase 22B.
It is not a live connector authorization, does not enable a static registry
dialect, and must not be treated as a network, WebSocket, REST, private API,
credential, or order-submission implementation.

## Operational Verification Status

Operational connector readiness: **blocked**.

The `docs.example.test` URLs and `deribit-phase22b-*` hashes below are fixture
placeholders. They may be used by offline tests to prove overlay mechanics, but
they are not production official-document references. They must be replaced by
real official source URLs, independently reproducible content hashes, positive
retrieval timestamps, and reviewer evidence before any operational verification
can pass.

`CONTENT_HASH_UNAVAILABLE`, missing hashes, missing retrieval timestamps,
summary-only Deep Research prose, and placeholder official-doc refs are all
fail-closed. Unknown operational fields remain blockers:

- public subscription rate limits
- max staleness
- max receive lag
- checksum semantics if ambiguous
- testnet versus production differences
- regional, legal, and access review

## Package Fields

- `package_id`: `deribit-public-book-phase22b-draft`
- `venue_id`: `deribit`
- `research_date`: `2026-05-09`
- `retrieved_at_ns`: `2200000000000`
- `source_count`: `5`
- `reviewer_id`: `phase22b-draft-review`
- `verifier_id`: `phase22b-offline-overlay-test`
- `rejection_reasons`: `[]`

## Evidence Items

Each item below requires a real official source URL, content hash, and retrieval
timestamp before it can be promoted outside offline tests.

### Item 1: Initial Book Notification Snapshot

- `evidence_id`: `deribit:l2_orderbook:placeholder::initial-book-snapshot`
- `doc_url`: `https://docs.example.test/deribit/public-book-initial-snapshot`
- `source_name`: `supplied-deribit-official-doc-draft`
- `doc_type`: `l2_orderbook`
- `content_hash`: `deribit-phase22b-initial-snapshot-hash`
- `retrieved_at_ns`: `2200000000001`
- `cited_claim_text`: First public WebSocket book notification is a snapshot.
- `official_source_citation`: supplied Phase 22B Deribit research fact 1.
- `verification_status`: `verified` for offline fixture use only.
- `rejection_reasons`: `[]`

### Item 2: Subsequent Book Notifications Are Deltas

- `evidence_id`: `deribit:l2_orderbook:placeholder::subsequent-book-deltas`
- `doc_url`: `https://docs.example.test/deribit/public-book-deltas`
- `source_name`: `supplied-deribit-official-doc-draft`
- `doc_type`: `l2_orderbook`
- `content_hash`: `deribit-phase22b-delta-hash`
- `retrieved_at_ns`: `2200000000002`
- `cited_claim_text`: Subsequent public book notifications are incremental deltas.
- `official_source_citation`: supplied Phase 22B Deribit research fact 2.
- `verification_status`: `verified` for offline fixture use only.
- `rejection_reasons`: `[]`

### Item 3: Change Id Continuity

- `evidence_id`: `deribit:l2_orderbook:placeholder::change-id-continuity`
- `doc_url`: `https://docs.example.test/deribit/public-book-change-id`
- `source_name`: `supplied-deribit-official-doc-draft`
- `doc_type`: `l2_orderbook`
- `content_hash`: `deribit-phase22b-change-id-hash`
- `retrieved_at_ns`: `2200000000003`
- `cited_claim_text`: Book deltas carry `change_id` and `prev_change_id` continuity.
- `official_source_citation`: supplied Phase 22B Deribit research fact 3.
- `verification_status`: `verified` for offline fixture use only.
- `rejection_reasons`: `[]`

### Item 4: Prev Change Id Mismatch Requires Resync

- `evidence_id`: `deribit:l2_orderbook:placeholder::prev-change-id-resync`
- `doc_url`: `https://docs.example.test/deribit/public-book-resync`
- `source_name`: `supplied-deribit-official-doc-draft`
- `doc_type`: `l2_orderbook`
- `content_hash`: `deribit-phase22b-resync-hash`
- `retrieved_at_ns`: `2200000000004`
- `cited_claim_text`: `prev_change_id` mismatch requires resubscribe or resync.
- `official_source_citation`: supplied Phase 22B Deribit research fact 4.
- `verification_status`: `verified` for offline fixture use only.
- `rejection_reasons`: `[]`

### Item 5: Zero Gap Tolerance

- `evidence_id`: `deribit:l2_orderbook:placeholder::max-gap-tolerance-zero`
- `doc_url`: `https://docs.example.test/deribit/public-book-gap-tolerance`
- `source_name`: `supplied-deribit-official-doc-draft`
- `doc_type`: `l2_orderbook`
- `content_hash`: `deribit-phase22b-gap-tolerance-hash`
- `retrieved_at_ns`: `2200000000005`
- `cited_claim_text`: `max_gap_tolerance` is zero for the offline Deribit L2 continuity model.
- `official_source_citation`: supplied Phase 22B Deribit research fact 5.
- `verification_status`: `verified` for offline fixture use only.
- `rejection_reasons`: `[]`

## Dialect Claim Mapping

- `supported_dialect_id`: `deribit:l2_orderbook:placeholder`
- `supported_feed_type`: `l2_orderbook`
- `sequence_model_evidence`: `change_id` / `prev_change_id` continuity maps to `prev_final_range`.
- `checksum_model_evidence`: Not supplied. Keep checksum model `none` or fail closed if checksum is required.
- `heartbeat_ping_pong_evidence`: Not supplied.
- `snapshot_delta_resync_evidence`: Initial notification is snapshot, subsequent notifications are deltas, and mismatch requires resubscribe or resync.
- `rate_limit_evidence`: Not supplied.
- `regional_legal_access_evidence`: Not supplied.
- `max_staleness_ns_evidence`: Not supplied.
- `max_receive_lag_ns_evidence`: Not supplied.

## Safety Warnings

- Do not include secrets.
- Do not include API keys.
- Do not include passphrases, tokens, private keys, or account identifiers.
- Do not convert this draft into static registry verification.
- Do not enable connector readiness globally from this draft.
- Do not treat placeholder URLs or placeholder hashes as operational evidence.
- Do not treat summary-only Deep Research text as verified official evidence.
- Unknown operational fields remain fail-closed until official source evidence is supplied.
