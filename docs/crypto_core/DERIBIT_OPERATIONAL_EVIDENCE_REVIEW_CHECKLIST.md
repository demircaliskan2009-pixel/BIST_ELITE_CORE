# Deribit Operational Evidence Review Checklist

Status: manual review gate / operational evidence blocker checklist.

This checklist is an offline evidence acquisition and review gate for the
Deribit public L2 order-book dialect. Completing this document does not create a
connector, authorize network access, enable static registry readiness, or permit
orders or live execution. It only records whether the evidence needed by the
fail-closed operational readiness gate has been acquired and reviewed.

## Gate Status

- `checklist_id`: `deribit-operational-evidence-review-phase22i`
- `venue_id`: `deribit`
- `dialect_id`: `deribit:l2_orderbook:placeholder`
- `feed_type`: `l2_orderbook`
- `operational_status`: `BLOCKED`
- `manual_review_required`: `YES`
- `manual_hash_required`: `YES`
- `enabled_for_connector`: `false`
- `static_registry_verified`: `false`
- `connector_ready_dialects_expected`: `[]`

## Required Evidence Acquisition Fields

Every Deribit operational evidence claim remains blocked until all fields below
are populated from official Deribit sources, independently reviewed, and mapped
back to the evidence package.

- `official_source_url_per_claim`: `BLOCKER`
  - Requirement: every claim has a real official source URL.
- `retrieval_timestamp`: `BLOCKER`
  - Requirement: every source snapshot has a positive retrieval timestamp.
- `reproducible_sha256_content_hash`: `BLOCKER`
  - Requirement: every source snapshot has a reproducible SHA256/content hash.
- `reviewer_id`: `BLOCKER`
  - Requirement: a reviewer id is recorded for the manual review.
- `review_timestamp`: `BLOCKER`
  - Requirement: a positive review timestamp is recorded.
- `manual_approval_status`: `BLOCKER`
  - Requirement: manual approval status is explicit and approved before use.
- `sequence_change_id_prev_change_id_proof_reviewed`: `BLOCKER`
  - Requirement: sequence, `change_id`, and `prev_change_id` proof reviewed.
- `snapshot_delta_resync_proof_reviewed`: `BLOCKER`
  - Requirement: snapshot, delta, and resync proof reviewed.
- `checksum_decision_reviewed`: `BLOCKER`
  - Requirement: checksum model or fail-closed checksum absence reviewed.
- `heartbeat_ping_pong_liveness_proof_reviewed`: `BLOCKER`
  - Requirement: heartbeat, ping-pong, and liveness proof reviewed.
- `rate_subscription_limit_proof_reviewed`: `BLOCKER`
  - Requirement: rate and subscription limit proof reviewed.
- `staleness_budget_defined`: `BLOCKER`
  - Requirement: max staleness budget is defined from official evidence.
- `receive_lag_budget_defined`: `BLOCKER`
  - Requirement: max receive-lag budget is defined from official evidence.
- `testnet_prod_difference_reviewed`: `BLOCKER`
  - Requirement: testnet and production differences are reviewed.
- `regional_legal_access_reviewed`: `BLOCKER`
  - Requirement: regional, legal, and access constraints are reviewed.

## Safety Review Fields

These safety checks must remain true while the checklist is incomplete.

- `no_secrets_api_keys_in_docs`: `REQUIRED`
  - Requirement: docs contain no secrets, API keys, tokens, passphrases, private
    keys, account identifiers, or environment-variable based credentials.
- `static_registry_remains_unverified`: `REQUIRED`
  - Requirement: the Deribit static dialect remains unverified and disabled.
- `connector_ready_dialects_remains_empty`: `REQUIRED`
  - Requirement: `connector_ready_dialects()` remains empty.
- `no_real_connector_network_client_orders_live`: `REQUIRED`
  - Requirement: no real connector, network, REST, WebSocket client, endpoint,
    private API, order path, or live execution path is introduced.

## Completion Rule

The Deribit evidence package remains operationally blocked until every
`BLOCKER` item above is satisfied with official-source evidence, reproducible
hashes, retrieval timestamps, reviewer metadata, manual approval, and explicit
budget decisions. Even after completion, a separate registry enablement and
connector implementation phase is required before any runtime connector can
exist.
