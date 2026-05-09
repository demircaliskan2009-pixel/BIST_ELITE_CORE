# Official Venue Evidence Package Template

This template is for storing caller-supplied official public-feed research evidence.
It is an offline evidence intake format only. It must not fetch docs, open network
connections, read credentials, or imply connector readiness by itself.

## Package Fields

- `package_id`: Stable local evidence package id.
- `venue_id`: Canonical venue id from `VenueId`.
- `research_date`: Human-readable research date.
- `retrieved_at_ns`: Positive integer retrieval timestamp.
- `source_count`: Number of official evidence items in the package.
- `reviewer_id`: Human or process id responsible for this package.
- `verifier_id`: Human or process id responsible for verification.
- `rejection_reasons`: Explicit fail-closed reasons, or empty when none.

## Evidence Item Fields

Each official evidence item must preserve exact source mapping:

- `evidence_id`: Stable id, prefixed by supported `dialect_id`.
- `doc_url`: Official source URL.
- `source_name`: Official source name.
- `doc_type`: Feed type, such as `l2_orderbook`.
- `content_hash`: Hash of the retrieved official source content.
- `retrieved_at_ns`: Positive integer retrieval timestamp for the source.
- `cited_claim_text`: Exact claim text or narrow paraphrase anchored to the source.
- `official_source_citation`: Citation label, section, or anchor from the official source.
- `verification_status`: `verified`, `supplied`, `unknown`, or `rejected`.
- `rejection_reasons`: Explicit fail-closed reasons, or empty when none.

## Dialect Claim Mapping

Every dialect claim must be backed by one or more official evidence items:

- `supported_dialect_id`: Dialect id that this evidence supports.
- `supported_feed_type`: Public feed type that this evidence supports.
- `sequence_model_evidence`: Evidence for sequence model selection.
- `checksum_model_evidence`: Evidence for checksum model selection.
- `heartbeat_ping_pong_evidence`: Evidence for heartbeat, ping, or pong behavior.
- `snapshot_delta_resync_evidence`: Evidence for snapshot, delta, and resync behavior.
- `rate_limit_evidence`: Evidence for limits, if supplied.

## Safety Warnings

- Do not include secrets.
- Do not include API keys.
- Do not include passphrases, tokens, private keys, or account identifiers.
- Do not mark `verification_status` as `verified` without an official source URL,
  content hash, and retrieval timestamp.
- Deep Research summaries alone are not enough unless they cite official docs and
  preserve exact claim mapping.
- Connector readiness remains false until the evidence bundle and overlay pass
  fail-closed tests.
