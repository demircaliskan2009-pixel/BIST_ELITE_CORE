# Deribit Official Excerpt Audit - Phase 26AA

status: EXCERPT_AUDIT_ONLY
phase: 26AA
generated_at: 2026-05-18
NOT_an_approval: true
NOT_worksheet_mutation: true
NOT_connector_enablement: true
NOT_b1_b5_closure: true

## Purpose

Phase 26AA audits all 26 remaining pending rows from committed repo evidence
only. For each row the classification is one of:

- `EXCERPT_PROOF_READY`: committed official snapshot/worksheet text is enough.
- `NEEDS_EXTERNAL_RESEARCH`: repo lacks a verbatim or paraphrased excerpt from
  the hashed documentation source; operator must read the hashed page and
  commit the excerpt.
- `NEEDS_POLICY_DECISION`: depends on an operator-defined engineering policy
  value; no official documentation excerpt can supply the value.
- `NEEDS_LEGAL_REVIEW`: depends on a jurisdiction/legal decision that requires
  human legal review.

No external web claims are made here. All references are to committed repo
files only.

## Evidence Basis

| committed_artifact | path | relevance |
|---|---|---|
| Source snapshot manifest | `docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md` | SHA-256 hashes for 6 source IDs. All `retrieval_status=REVIEWED_APPROVED`. |
| Claim review worksheet | `docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md` | Maps each claim to source_id, URL, anchor. All pending rows have `review_status=PENDING`. |
| Policy worksheet | `docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md` | 7 policy rows all `policy_status=PENDING`. |
| Gap doc 26Y | `docs/crypto_core/DERIBIT_CHANNEL_OFFICIAL_EXCERPT_GAP_26Y.md` | 4 book-channel excerpt gaps documented. |
| Blocker summary 26Z | `docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_26Z.md` | 26-row inventory of all pending blockers. |

## Same-Hash Caveat (from committed worksheet)

All 6 source snapshot IDs share SHA-256
`a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd` and size
939778 bytes. This proves only that the documentation payload was fetched and
hashed locally at Phase 22L. It does NOT prove claim-level review,
section-level content, or any specific documentation claim. Raw HTML is NOT
committed. The hash cannot substitute for a committed verbatim excerpt.

## NO_EXCERPT_PROOF_READY_ROWS

No row in the 26-row pending inventory is classified as `EXCERPT_PROOF_READY`.

Reason: The only committed artefacts are (a) hashes of the documentation pages
and (b) the claim and policy worksheets that record what needs to be reviewed.
No committed file in the repo contains verbatim or paraphrased text extracted
from the Deribit official documentation pages. Therefore no documentation claim
can be considered proven from repo evidence alone.

Phase 26AB is accordingly SKIPPED (see section below).

## Row Classifications

### Raw-Sequence Artifact Blockers (4 rows)

These rows require both a committed official excerpt identifying the emitting
channel and an accepted raw smoke artifact from that channel.

| row_id | source_id | worksheet_anchor | classification | reason |
|---|---|---|---|---|
| `claim_review:prev_change_id` | `DERIBIT_NOTIFICATIONS` | `#notifications` | `NEEDS_EXTERNAL_RESEARCH` | No committed excerpt from notifications book-channel section confirming which channel format emits non-null `prev_change_id`. Excerpt gap `BOOK_CHANNEL_FORMAT_VARIANTS` documented in 26Y. |
| `claim_review:continuity_condition` | `DERIBIT_NOTIFICATIONS` | `#notifications` | `NEEDS_EXTERNAL_RESEARCH` | Depends on `prev_change_id` channel excerpt (gap `BOOK_CHANNEL_FORMAT_VARIANTS`) and on continuity rule excerpt (gap `BOOK_CONTINUITY_GAP_RECOVERY_RULE`). Neither committed. |
| `claim_review:first_message_snapshot` | `DERIBIT_NOTIFICATIONS` | `#notifications` | `NEEDS_EXTERNAL_RESEARCH` | No committed excerpt confirming first-message snapshot semantics. Excerpt gap `BOOK_SNAPSHOT_DELTA_SEMANTICS` documented in 26Y. |
| `claim_review:incremental_delta` | `DERIBIT_NOTIFICATIONS` | `#notifications` | `NEEDS_EXTERNAL_RESEARCH` | No committed excerpt confirming incremental-delta semantics. Excerpt gap `BOOK_SNAPSHOT_DELTA_SEMANTICS` documented in 26Y. Depends on type-emitting channel. |

### Documentation Artifact Blockers (13 rows — external research required)

| row_id | source_id | worksheet_anchor | classification | required_excerpt |
|---|---|---|---|---|
| `claim_review:public_rest_availability` | `DERIBIT_INSTRUMENTS` | `#public-get_instruments` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_INSTRUMENTS` page and commits excerpt from `#public-get_instruments` section confirming public REST availability without authentication. |
| `claim_review:prod_testnet_ws_endpoint` | `DERIBIT_ENVIRONMENT` | `#json-rpc-over-websocket` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_ENVIRONMENT` page and commits excerpt from `#json-rpc-over-websocket` section listing production and testnet WebSocket endpoint URLs. |
| `claim_review:prod_testnet_rest_endpoint` | `DERIBIT_INSTRUMENTS` | `#public-get_instruments` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_INSTRUMENTS` page and commits excerpt from `#public-get_instruments` section listing production and testnet REST endpoint base URLs. |
| `claim_review:rest_snapshot_requirement` | `DERIBIT_NOTIFICATIONS` | `#notifications` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_NOTIFICATIONS` page and commits excerpt from book-channel continuity section. Excerpt gap `BOOK_CONTINUITY_GAP_RECOVERY_RULE` (26Y Gap 3). |
| `claim_review:checksum_decision` | `DERIBIT_NOTIFICATIONS` | `#notifications` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_NOTIFICATIONS` page and commits excerpt from book-channel section on checksum field. Excerpt gap `BOOK_CHECKSUM_FIELD` (26Y Gap 4). Also has paired policy row. |
| `claim_review:gap_resubscribe_rule` | `DERIBIT_NOTIFICATIONS` | `#notifications` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_NOTIFICATIONS` page and commits excerpt from continuity section. Excerpt gap `BOOK_CONTINUITY_GAP_RECOVERY_RULE` (26Y Gap 3). |
| `claim_review:heartbeat_liveness_proof` | `DERIBIT_ENVIRONMENT` | `#json-rpc-over-websocket` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_ENVIRONMENT` page and commits excerpt from `#json-rpc-over-websocket` section on heartbeat/ping-pong/liveness semantics. |
| `claim_review:public_rate_subscription_limits` | `DERIBIT_RATE_LIMITS` | `#rate-limits` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_RATE_LIMITS` page and commits excerpt from `#rate-limits` section on public WebSocket subscription rate limits. |
| `claim_review:public_trades` | `DERIBIT_NOTIFICATIONS` | `#notifications` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_NOTIFICATIONS` page and commits excerpt from trades channel section confirming public trades channel format and semantics. |
| `claim_review:ticker` | `DERIBIT_TICKER` | `#ticker-instrument_name-interval` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_TICKER` page and commits excerpt from `#ticker-instrument_name-interval` section confirming ticker channel format and update frequency. |
| `claim_review:mark_index_funding_open_interest` | `DERIBIT_TICKER` | `#ticker-instrument_name-interval` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_TICKER` page and commits excerpt from `#ticker-instrument_name-interval` section confirming mark, index, funding, and open-interest data fields. |
| `claim_review:testnet_prod_difference` | `DERIBIT_ENVIRONMENT` | `#json-rpc-over-websocket` | `NEEDS_EXTERNAL_RESEARCH` | Operator reads hashed `DERIBIT_ENVIRONMENT` page and commits excerpt from environment section enumerating known testnet vs. production differences. |

### Documentation Artifact Blockers (2 rows — policy decision required, no doc excerpt is sufficient)

| row_id | source_id | classification | reason |
|---|---|---|---|
| `claim_review:staleness_budget` | `DERIBIT_NOTIFICATIONS` | `NEEDS_POLICY_DECISION` | Maximum staleness budget is an engineering/operator decision for our system. No official Deribit documentation defines a staleness budget value for consuming systems. Depends on `policy_review:staleness_budget`. |
| `claim_review:receive_lag_budget` | `DERIBIT_NOTIFICATIONS` | `NEEDS_POLICY_DECISION` | Maximum receive-lag budget is an engineering/operator decision. No official Deribit documentation defines a receive-lag budget for consuming systems. Depends on `policy_review:receive_lag_budget`. |

### Legal Review Blocker (1 row)

| row_id | source_id | worksheet_anchor | classification | reason |
|---|---|---|---|---|
| `claim_review:regional_legal_access` | `DERIBIT_RESTRICTED` | `#restricted-countries` | `NEEDS_LEGAL_REVIEW` | Operator reads hashed `DERIBIT_RESTRICTED` page and commits legal access review confirming the operating jurisdiction has no Deribit API restriction. No Turkey-specific approval is committed. Depends on `policy_review:regional_legal_access_review`. |

### Policy Review Blockers (6 rows — operator decision required)

| row_id | source_id | classification | reason |
|---|---|---|---|
| `policy_review:checksum_decision` | `DERIBIT_NOTIFICATIONS` | `NEEDS_POLICY_DECISION` | Operator must decide whether to implement or explicitly waive checksum validation. Requires documentation excerpt first (`claim_review:checksum_decision`). |
| `policy_review:liveness_policy` | `DERIBIT_ENVIRONMENT` | `NEEDS_POLICY_DECISION` | Operator must define liveness detection and reconnection policy. Requires documentation excerpt first (`claim_review:heartbeat_liveness_proof`). |
| `policy_review:staleness_budget` | `DERIBIT_NOTIFICATIONS` | `NEEDS_POLICY_DECISION` | Operator must approve maximum staleness budget. |
| `policy_review:receive_lag_budget` | `DERIBIT_NOTIFICATIONS` | `NEEDS_POLICY_DECISION` | Operator must approve maximum receive-lag budget. |
| `policy_review:testnet_prod_review` | `DERIBIT_ENVIRONMENT` | `NEEDS_POLICY_DECISION` | Operator must confirm testnet vs. production difference implications. Requires documentation excerpt first (`claim_review:testnet_prod_difference`). |
| `policy_review:separate_connector_enablement` | `DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST` | `NEEDS_POLICY_DECISION` | Operator must separately authorize connector enablement after all B1-B5 blockers are resolved. Cannot be completed in this evidence phase. |

### Legal Policy Review Blocker (1 row)

| row_id | source_id | classification | reason |
|---|---|---|---|
| `policy_review:regional_legal_access_review` | `DERIBIT_RESTRICTED` | `NEEDS_LEGAL_REVIEW` | Human legal review required. Cannot be completed by engineering alone. |

## Classification Summary

| classification | count | row_ids |
|---|---|---|
| `EXCERPT_PROOF_READY` | 0 | — |
| `NEEDS_EXTERNAL_RESEARCH` | 16 | `prev_change_id`, `continuity_condition`, `first_message_snapshot`, `incremental_delta`, `public_rest_availability`, `prod_testnet_ws_endpoint`, `prod_testnet_rest_endpoint`, `rest_snapshot_requirement`, `checksum_decision`, `gap_resubscribe_rule`, `heartbeat_liveness_proof`, `public_rate_subscription_limits`, `public_trades`, `ticker`, `mark_index_funding_open_interest`, `testnet_prod_difference` |
| `NEEDS_POLICY_DECISION` | 8 | `staleness_budget` (claim), `receive_lag_budget` (claim), `checksum_decision` (policy), `liveness_policy`, `staleness_budget` (policy), `receive_lag_budget` (policy), `testnet_prod_review`, `separate_connector_enablement` |
| `NEEDS_LEGAL_REVIEW` | 2 | `regional_legal_access` (claim), `regional_legal_access_review` (policy) |
| **TOTAL** | **26** | |

## Phase 26AB: SKIPPED

No rows are classified as `EXCERPT_PROOF_READY`. Therefore Phase 26AB (excerpt
proof batch) is skipped. No `DERIBIT_OFFICIAL_EXCERPT_PROOF_BATCH_26AB.md` is
created.

The commit that would contain 26AB is not made. Phase 26AC contains a
classification batch that promotes 0 rows (all remain WAIT_INSUFFICIENT /
WAIT_POLICY / WAIT_LEGAL).

## Operator Next Steps

| priority | action | affected_rows |
|---|---|---|
| 1 | Read `DERIBIT_NOTIFICATIONS` (hashed at Phase 22L) and commit book-channel section excerpt covering channel format variants, snapshot/delta semantics, continuity rule, gap recovery, and checksum field. | `prev_change_id`, `continuity_condition`, `first_message_snapshot`, `incremental_delta`, `rest_snapshot_requirement`, `checksum_decision`, `gap_resubscribe_rule` |
| 2 | Read `DERIBIT_ENVIRONMENT` (hashed at Phase 22L) and commit excerpt from `#json-rpc-over-websocket` covering endpoint URLs, testnet differences, and heartbeat/liveness semantics. | `prod_testnet_ws_endpoint`, `heartbeat_liveness_proof`, `testnet_prod_difference` |
| 3 | Read `DERIBIT_INSTRUMENTS` (hashed at Phase 22L) and commit excerpt from `#public-get_instruments` covering public REST availability and endpoint base URLs. | `public_rest_availability`, `prod_testnet_rest_endpoint` |
| 4 | Read `DERIBIT_RATE_LIMITS` (hashed at Phase 22L) and commit excerpt from `#rate-limits` covering public subscription rate limits. | `public_rate_subscription_limits` |
| 5 | Read `DERIBIT_TICKER` (hashed at Phase 22L) and commit excerpt from `#ticker-instrument_name-interval` covering ticker channel format and mark/index/funding/OI fields. | `ticker`, `mark_index_funding_open_interest` |
| 6 | Read `DERIBIT_RESTRICTED` (hashed at Phase 22L) and commit legal access review. | `regional_legal_access`, `regional_legal_access_review` |
| 7 | Read public trades section in `DERIBIT_NOTIFICATIONS` and commit excerpt. | `public_trades` |
| 8 | After documentation excerpts are committed, make engineering policy decisions on staleness budget, receive-lag budget, liveness policy, and checksum handling. | `staleness_budget`, `receive_lag_budget`, `liveness_policy`, `checksum_decision` (policy) |

## Safety Statement

This document is:
- NOT a channel claim approval
- NOT a worksheet mutation
- NOT a connector enablement
- NOT a B1-B5 gate closure
- NOT a synthetic observation of Deribit server behavior
- NOT a claim that any documentation excerpt content is known

`pending_rows = 26` (confirmed by `evaluate_deribit_manual_review_readiness()`).
B1-B5 remain BLOCKED.
`connector_ready_dialects() == ()`.
No rows promoted to PROOF_READY_NOT_APPROVED.
