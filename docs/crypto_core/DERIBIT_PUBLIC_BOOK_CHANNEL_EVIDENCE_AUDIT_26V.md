# Deribit Public Book Channel Evidence Audit - Phase 26V

status: CHANNEL_AUDIT_ONLY
phase: 26V
generated_at: 2026-05-18
supersedes: N/A (first channel audit)
NOT_an_approval: true
NOT_worksheet_mutation: true
NOT_connector_enablement: true
NOT_b1_b5_closure: true

## Purpose

Audit all repo-committed evidence to classify known and candidate Deribit
public book channel subscription formats. Determine whether any candidate
channel is supported by official repo evidence for capture.

## Current Channel

| field | value |
|---|---|
| channel | `book.BTC-PERPETUAL.none.10.100ms` |
| harness constant | `DERIBIT_DEFAULT_PUBLIC_CHANNEL` |
| source file | `src/crypto_core/data/deribit_public_ws_harness.py` line 10 |
| phase_26s_finding | All 9 captured events return `payload_sample.prev_change_id=null` and `payload_sample.type=null`. |
| channel_class | aggregated_order_book |
| emits_prev_change_id | false |
| emits_type_field | false |

This is the aggregated order book format: `book.<instrument>.<group_size>.<interval>`.
Aggregated channels deliver price-level summaries, not raw incremental deltas.
They do not emit `prev_change_id` or `type` per Phase 26S observation.

## Harness Channel Filter

The harness enforces two filter layers in `_channel_allowed()`:

### Forbidden Token Filter

```
_FORBIDDEN_CHANNEL_TOKENS = (
    "user", "private", "auth", "raw", "order",
    "portfolio", "position", "account",
)
```

Source: `src/crypto_core/data/deribit_public_ws_harness.py` lines 17-26.

Any channel string containing `"raw"` as a substring is unconditionally
rejected by this filter.

### Aggregated Pattern Filter

```
_AGGREGATED_CHANNEL_PATTERNS = (
    re.compile(r"^book\.<instrument>\.none\.<group>\.100ms$"),
    re.compile(r"^trades\.<instrument>\.100ms$"),
    re.compile(r"^ticker\.<instrument>\.100ms$"),
)
```

Source: `src/crypto_core/data/deribit_public_ws_harness.py` lines 28-32.

The book pattern requires the `.none.<group>` component (group = 1|10|20|50|100).
Channels without this component (e.g. `book.BTC-PERPETUAL.100ms`) do not match.

## Candidate Channel Classification

| candidate_channel | classification | classification_code | evidence_basis | action_needed |
|---|---|---|---|---|
| `book.BTC-PERPETUAL.none.10.100ms` | confirmed_no_target_fields | confirmed_baseline | Phase 26S artifact: 9 events, all `prev_change_id=null`, all `type=null` | None — confirmed inadequate |
| `book.BTC-PERPETUAL.100ms` | needs_official_excerpt | B | Mentioned as speculative candidate in 26U/26S docs ("e.g."). No official excerpt in repo confirms this format emits `prev_change_id` or `type`. Harness pattern does not match this format. | (1) Operator commits official excerpt from `DERIBIT_NOTIFICATIONS` confirming channel format and fields; (2) Operator authorizes harness pattern addition; (3) Capture may proceed. |
| `book.BTC-PERPETUAL.raw` | unsupported | C | `"raw"` is in `_FORBIDDEN_CHANNEL_TOKENS`. Harness rejects any channel containing this token. No repo-committed official excerpt justifies removing "raw" from the forbidden token list. | Not actionable without (1) official excerpt proving this is a safe public channel, (2) operator authorization to remove "raw" from forbidden tokens, (3) security review. |
| Any other Deribit book channel | unsupported | C | No repo-committed evidence identifies any other book channel format. | Not actionable — guessing channel names is forbidden per system rules. |

## Classification Summary

| code | count | channels |
|---|---|---|
| A (channel_candidate_supported_by_repo) | 0 | — |
| B (needs_official_excerpt) | 1 | `book.BTC-PERPETUAL.100ms` |
| C (unsupported/no_action) | 2 | `book.BTC-PERPETUAL.raw`, all others |

**No A-class candidate exists.**

## Phase 26W Decision: SKIP

Because no channel candidate reaches classification A (supported by committed
official repo evidence), Phase 26W (channel-parametric capture) is skipped.

The smoke script already supports `--channel` flag (added in prior phase).
The workflow does not expose a channel input and the harness does not allow
the `book.BTC-PERPETUAL.100ms` format currently.

No script or workflow change is made in this phase.
No capture is dispatched.

## Evidence Gaps Identified

The following official excerpt is needed before any candidate channel can be
promoted to class A:

| gap_id | required_content | official_source | existing_repo_state |
|---|---|---|---|
| `BOOK_CHANNEL_FORMAT_VARIANTS` | Official doc excerpt listing all Deribit public book channel subscription variants, with exact format string (`book.<inst>.<interval>` vs `book.<inst>.<group>.<interval>`), and which fields each variant emits (`change_id`, `prev_change_id`, `type`). | `DERIBIT_NOTIFICATIONS` (`https://docs.deribit.com/#notifications`) | Source HTML fetched and hashed in Phase 22L (`source_id=DERIBIT_NOTIFICATIONS`, `sha256=a5770fc...`). Raw HTML not committed. No claim-level review of book channel variant section completed. |

## Repo References

| reference | location | relevance |
|---|---|---|
| Harness source | `src/crypto_core/data/deribit_public_ws_harness.py` | `_FORBIDDEN_CHANNEL_TOKENS`, `_AGGREGATED_CHANNEL_PATTERNS`, `_channel_allowed()` |
| Phase 26S proof | `docs/crypto_core/DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26S.json` | Confirmed `prev_change_id=null`, `type=null` for current channel |
| Phase 26S batch | `docs/crypto_core/DERIBIT_PROOF_ARTIFACT_BATCH_26S.md` | Channel limitation classification |
| Phase 26U blockers | `docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_26U.md` | Speculative channel mentions as "e.g." — not official evidence |
| Source manifest | `docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md` | `DERIBIT_NOTIFICATIONS` fetched/hashed only |
| Claim worksheet | `docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md` | All book sequence rows PENDING |

## Safety Invariants

| invariant | status |
|---|---|
| No worksheet edit | true |
| No connector enablement | true |
| No channel guessed without evidence | true |
| No harness pattern change | true |
| No forbidden token removal | true |
| pending_rows unchanged | 26 |
| B1-B5 remain BLOCKED | true |
