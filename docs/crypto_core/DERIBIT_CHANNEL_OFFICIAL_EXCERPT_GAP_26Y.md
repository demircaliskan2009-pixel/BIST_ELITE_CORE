# Deribit Channel Official Excerpt Gap - Phase 26Y

status: EXCERPT_GAP_ONLY
phase: 26Y
generated_at: 2026-05-18
NOT_an_approval: true
NOT_worksheet_mutation: true
NOT_connector_enablement: true
NOT_b1_b5_closure: true

## Purpose

Phase 26V determined that no repo-committed official excerpt identifies which
Deribit public book channel subscription format emits non-null `prev_change_id`
and `type`. Phase 26X (accepted artifact classification) is skipped because no
capture was dispatched. This document records the exact official excerpt gaps
that must be filled before any channel variant capture can proceed.

## Phase 26X Status: SKIPPED

| field | value |
|---|---|
| capture_dispatched | false |
| capture_run_id | N/A |
| artifact_accepted | N/A |
| classification_path | 26Y (gap only) |
| reason | No class-A channel candidate exists. No channel variant has repo-committed official proof of emitting `prev_change_id` or `type`. |

## Official Excerpt Gaps

All gaps reference `DERIBIT_NOTIFICATIONS` (`https://docs.deribit.com/#notifications`),
which was fetched and hashed in Phase 22L (`sha256=a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd`,
`content_size_bytes=939778`). The raw HTML is not committed. No claim-level review
of the following sections has been completed.

### Gap 1: Book Channel Format Variants

| field | value |
|---|---|
| gap_id | `BOOK_CHANNEL_FORMAT_VARIANTS` |
| official_source | `DERIBIT_NOTIFICATIONS` |
| official_url | `https://docs.deribit.com/#notifications` |
| section_anchor | `#book-instrument_name-group-interval` or equivalent book channel section |
| claim_ids | `prev_change_id`, `continuity_condition`, `first_message_snapshot`, `incremental_delta` |
| required_excerpt_content | Exact subscription format strings for Deribit public book channels. Specifically: (1) Does `book.<instrument_name>.<interval>` exist as a distinct channel format (without the `<group>` component)? (2) Does `book.<instrument_name>.<group>.<interval>` describe only the aggregated variant? (3) Which format emits `prev_change_id` as a non-null integer? (4) Which format emits a `type` field with values `snapshot` or `change`? |
| current_repo_state | Not committed. Phase 22L hash proves the documentation page was fetched; it does not prove section-level review. |
| required_artifact | `docs/crypto_core/official_sources/deribit/20260510/DERIBIT_NOTIFICATIONS_BOOK_CHANNEL_EXCERPT.md` — committed verbatim or paraphrased excerpt from the official Deribit notifications documentation book channel section, including all subscription format variants, field names, and semantic descriptions. |

### Gap 2: Snapshot vs Incremental Delta Semantics

| field | value |
|---|---|
| gap_id | `BOOK_SNAPSHOT_DELTA_SEMANTICS` |
| official_source | `DERIBIT_NOTIFICATIONS` |
| official_url | `https://docs.deribit.com/#notifications` |
| section_anchor | Book channel section |
| claim_ids | `first_message_snapshot`, `incremental_delta` |
| required_excerpt_content | (1) Does the first message after subscription always have `type == "snapshot"`? (2) Do subsequent messages have `type == "change"` or `"delta"`? (3) Is there a case where the first message is already incremental? (4) What triggers a re-snapshot (e.g. gap, reconnect)? |
| current_repo_state | Not committed. `DERIBIT_BOOK_PARSE_SEQUENCE_PROOF.json` Phase 25L documents harness capability only — no live snapshot/delta sequence observed. |
| required_artifact | Same as Gap 1 artifact or a separate `DERIBIT_NOTIFICATIONS_SNAPSHOT_DELTA_EXCERPT.md`. |

### Gap 3: Continuity Rule and Gap Recovery

| field | value |
|---|---|
| gap_id | `BOOK_CONTINUITY_GAP_RECOVERY_RULE` |
| official_source | `DERIBIT_NOTIFICATIONS` |
| official_url | `https://docs.deribit.com/#notifications` |
| section_anchor | Book channel section — change_id continuity note |
| claim_ids | `continuity_condition`, `gap_resubscribe_rule`, `rest_snapshot_requirement` |
| required_excerpt_content | (1) Does the official documentation define `prev_change_id[n] == change_id[n-1]` as the continuity invariant? (2) What action does Deribit recommend if a gap is detected? (3) Is a REST snapshot required to re-anchor after a gap, or is resubscription sufficient? |
| current_repo_state | Not committed. Claim worksheet rows `continuity_condition`, `gap_resubscribe_rule`, `rest_snapshot_requirement` all PENDING. |
| required_artifact | `docs/crypto_core/official_sources/deribit/20260510/DERIBIT_NOTIFICATIONS_CONTINUITY_EXCERPT.md`. |

### Gap 4: Checksum Field

| field | value |
|---|---|
| gap_id | `BOOK_CHECKSUM_FIELD` |
| official_source | `DERIBIT_NOTIFICATIONS` |
| official_url | `https://docs.deribit.com/#notifications` |
| section_anchor | Book channel section |
| claim_ids | `checksum_decision` |
| required_excerpt_content | (1) Is a `checksum` field present in book channel messages? (2) What algorithm is used? (3) Is it required for correct book reconstruction? |
| current_repo_state | Not committed. Policy row `checksum_decision` PENDING. |
| required_artifact | Same as Gap 1 artifact (checksum field description in book channel section). |

## Harness Constraint Summary

These constraints apply regardless of which channel excerpt is eventually committed:

| constraint | description |
|---|---|
| `"raw"` is a forbidden token | `_FORBIDDEN_CHANNEL_TOKENS` includes `"raw"`. Any channel containing `"raw"` as a substring is rejected by `_channel_allowed()`. If official docs describe a channel called `book.BTC-PERPETUAL.raw`, operator must explicitly authorize removing `"raw"` from the forbidden list after security review. |
| Aggregated pattern required | `_AGGREGATED_CHANNEL_PATTERNS` only matches `book.<inst>.none.<group>.100ms`, `trades.<inst>.100ms`, and `ticker.<inst>.100ms`. Any new channel format requires a new pattern added by the operator after reading official docs. |
| No channel added without authorization | The operator must read the official excerpt, identify the exact channel format string, and explicitly authorize the pattern addition in a separate patch. |

## Required Operator Actions

| priority | action |
|---|---|
| 1 | Operator reads `DERIBIT_NOTIFICATIONS` section on book channel subscriptions (the page was fetched in Phase 22L). |
| 2 | Operator commits exact verbatim or paraphrased excerpt from that section as `DERIBIT_NOTIFICATIONS_BOOK_CHANNEL_EXCERPT.md`. |
| 3 | Operator identifies the exact channel format string that emits `prev_change_id` (non-null integer) and `type` (`snapshot` / `change`). |
| 4 | Operator authorizes adding that channel format to `_AGGREGATED_CHANNEL_PATTERNS` in `deribit_public_ws_harness.py` (if it is `book.<inst>.100ms` or similar, `"raw"` token prohibition may not apply). |
| 5 | After authorization: engineering adds the pattern, smoke is dispatched on the authorized channel, artifact is classified. |

## Safety Statement

This document is:
- NOT a channel claim approval
- NOT a worksheet mutation
- NOT a connector enablement
- NOT a B1-B5 gate closure
- NOT a synthetic observation of Deribit server behavior
- NOT a guessed channel name (no channel names appear here that are not already in prior docs)

`pending_rows = 26` (confirmed by `evaluate_deribit_manual_review_readiness()`).
B1-B5 remain BLOCKED.
`connector_ready_dialects() == ()`.
