# Deribit Official Docs Research Pack - Phase 26AE

status: OFFICIAL_CURRENT_RESEARCH_PACK_ONLY
phase: 26AE
generated_at: 2026-05-18
retrieval_date: 2026-05-18
source_policy: OFFICIAL_DERIBIT_DOCS_ONLY
NOT_an_approval: true
NOT_worksheet_mutation: true
NOT_connector_enablement: true
NOT_b1_b5_closure: true
NOT_legal_approval: true

## Scope

Phase 26AE resolves the external documentation gap for the 16 Deribit rows
listed in the operator prompt. Evidence is taken only from current official
Deribit documentation and official Deribit Support content. This pack does not
mutate worksheets, does not fill reviewer metadata, does not approve claims,
does not authorize connector enablement, and does not add runtime behavior.

This pack is documentation evidence only. It is not an observed smoke artifact
and does not synthesize any Deribit server values.

## Official Source Ledger

| source_id | official_url_anchor | section_title | retrieval_date | use |
|---|---|---|---|---|
| `S1_ENVIRONMENTS` | `https://docs.deribit.com/index.html#environments` | `Welcome to Deribit API` / `Environments` | `2026-05-18` | Production and test environment endpoint proof. |
| `S2_JSON_RPC_TRANSPORTS` | `https://docs.deribit.com/articles/json-rpc-overview#transport-protocols` | `JSON-RPC 2.0 Protocol` / `Transport Protocols` | `2026-05-18` | HTTP REST and WebSocket endpoint proof. |
| `S3_BOOK_CHANNEL` | `https://docs.deribit.com/subscriptions/orderbook/bookinstrument_nameinterval#bookinstrument_nameinterval` | `book.(instrument_name).(interval)` | `2026-05-18` | Book channel snapshot, incremental update, `change_id`, `prev_change_id`, and continuity semantics. |
| `S4_NOTIFICATIONS_RELIABILITY` | `https://docs.deribit.com/articles/notifications#handling-missed-messages` | `Notifications` / `Handling Missed Messages` | `2026-05-18` | Gap detection and resubscribe recovery semantics. |
| `S5_REST_ORDER_BOOK` | `https://docs.deribit.com/api-reference/market-data/public-get_order_book#publicget_order_book` | `public/get_order_book` | `2026-05-18` | REST order book snapshot availability. |
| `S6_HEARTBEAT` | `https://docs.deribit.com/api-reference/session-management/public-set_heartbeat#publicset_heartbeat` | `public/set_heartbeat` | `2026-05-18` | WebSocket heartbeat, `test_request`, and stale connection proof. |
| `S7_RATE_LIMITS` | `https://docs.deribit.com/articles/rate-limits#rate-limits` | `Rate Limits` | `2026-05-18` | API and public subscription rate-limit proof. |
| `S8_TRADES_CHANNEL` | `https://docs.deribit.com/subscriptions/trades/tradesinstrument_nameinterval#tradesinstrument_nameinterval` | `trades.(instrument_name).(interval)` | `2026-05-18` | Public trades subscription proof. |
| `S9_TICKER_CHANNEL` | `https://docs.deribit.com/subscriptions/market-data/tickerinstrument_nameinterval#tickerinstrument_nameinterval` | `ticker.(instrument_name).(interval)` | `2026-05-18` | Ticker, mark, index, funding, and open interest proof. |
| `S10_RESTRICTED_JURISDICTIONS` | `https://support.deribit.com/hc/en-us/articles/25944487427741-Restricted-Jurisdictions` | `Restricted Jurisdictions` | `2026-05-18` | Documentation-only regional access restrictions. |

## Row Evidence

| row_id | classification_candidate | official_refs | evidence_summary |
|---|---|---|---|
| `public_rest_availability` | `PROOF_READY_NOT_APPROVED` | `S2_JSON_RPC_TRANSPORTS`, `S5_REST_ORDER_BOOK` | Official JSON-RPC documentation lists HTTPS endpoints for production and test, supports GET and POST, and the official `public/get_order_book` reference is under Market Data. |
| `prod_testnet_ws_endpoint` | `PROOF_READY_NOT_APPROVED` | `S1_ENVIRONMENTS`, `S2_JSON_RPC_TRANSPORTS` | Official documentation gives exact WebSocket endpoints: `wss://www.deribit.com/ws/api/v2` and `wss://test.deribit.com/ws/api/v2`. |
| `prod_testnet_rest_endpoint` | `PROOF_READY_NOT_APPROVED` | `S1_ENVIRONMENTS`, `S2_JSON_RPC_TRANSPORTS` | Official documentation gives exact HTTPS endpoints: `https://www.deribit.com/api/v2` and `https://test.deribit.com/api/v2`. |
| `rest_snapshot_requirement` | `PROOF_READY_NOT_APPROVED` | `S4_NOTIFICATIONS_RELIABILITY`, `S5_REST_ORDER_BOOK` | Official notification guidance says gap recovery can re-subscribe to obtain a full book snapshot; the REST order book method exists, but the cited recovery path does not require REST re-anchoring. |
| `gap_resubscribe_rule` | `PROOF_READY_NOT_APPROVED` | `S4_NOTIFICATIONS_RELIABILITY` | Official guidance says a `prev_change_id` mismatch indicates missed updates and the client should consider re-subscribing; after reconnecting, order book channels receive a full snapshot first. |
| `heartbeat_liveness_proof` | `PROOF_READY_NOT_APPROVED` | `S6_HEARTBEAT` | Official `public/set_heartbeat` says the WebSocket server sends heartbeat and `test_request` messages and closes the connection if the client fails to answer test requests. |
| `public_rate_subscription_limits` | `PROOF_READY_NOT_APPROVED` | `S7_RATE_LIMITS` | Official rate-limit documentation says all API traffic, including public traffic, follows rate limits, and lists a custom limit for `public/subscribe`. |
| `public_trades` | `PROOF_READY_NOT_APPROVED` | `S8_TRADES_CHANNEL` | Official trades subscription documentation shows `public/subscribe` to `trades.BTC-PERPETUAL.100ms` and describes executed trade notifications. |
| `ticker` | `PROOF_READY_NOT_APPROVED` | `S9_TICKER_CHANNEL` | Official ticker subscription documentation shows `public/subscribe` to `ticker.BTC-PERPETUAL.100ms` and describes real-time market data. |
| `mark_index_funding_open_interest` | `PROOF_READY_NOT_APPROVED` | `S9_TICKER_CHANNEL` | Official ticker data includes mark price, index price, current and 8-hour funding, and open interest fields. |
| `testnet_prod_difference` | `PROOF_READY_NOT_APPROVED` | `S1_ENVIRONMENTS`, `S2_JSON_RPC_TRANSPORTS` | Official docs state separate test and production environments with separate exact endpoint URLs and separate accounts/API keys for private methods. |
| `first_message_snapshot` | `PROOF_READY_NOT_APPROVED` | `S3_BOOK_CHANNEL`, `S4_NOTIFICATIONS_RELIABILITY` | Official order book docs say the first notification contains a full book snapshot, and reconnection handling says the first order book notification after re-subscribe is a full snapshot. |
| `incremental_delta` | `PROOF_READY_NOT_APPROVED` | `S3_BOOK_CHANNEL` | Official order book docs say later notifications contain only incremental level changes and define `new`, `change`, and `delete` actions. |
| `prev_change_id` | `PROOF_READY_NOT_APPROVED` | `S3_BOOK_CHANNEL`, `S4_NOTIFICATIONS_RELIABILITY` | Official order book docs say every message except the first contains `prev_change_id`. |
| `continuity_condition` | `PROOF_READY_NOT_APPROVED` | `S3_BOOK_CHANNEL`, `S4_NOTIFICATIONS_RELIABILITY` | Official order book docs define continuity by equality between current `prev_change_id` and the previous message `change_id`; matching values indicate no missed messages. |
| `regional_legal_access` | `DOCUMENTATION_PROOF_READY` | `S10_RESTRICTED_JURISDICTIONS` | Official Support lists restricted jurisdictions and states that access and use are not allowed for listed locations. This is documentation evidence only and does not approve legal access for any operator or jurisdiction. |

## Ambiguity Guardrails

| row_id | classification | reason |
|---|---|---|
| `checksum_decision` | `WAIT_INSUFFICIENT` | Not in Phase 26AE prompt scope, and this pack does not cite an official checksum field or checksum recovery requirement. |
| `staleness_budget` | `WAIT_POLICY` | Requires an operator-defined engineering budget, not an external documentation excerpt alone. |
| `receive_lag_budget` | `WAIT_POLICY` | Requires an operator-defined engineering budget, not an external documentation excerpt alone. |
| `regional_legal_access_review` | `WAIT_LEGAL` | Documentation evidence is not legal approval and does not replace human legal review. |

## Safety Statement

- No real worksheet was edited.
- No final `APPROVE`, `REJECT`, or `DEFER` was written to a worksheet.
- No `reviewer_id` or `reviewed_at_iso` final value was supplied.
- No connector readiness, registry enablement, private API, order path, or runtime client changed.
- `regional_legal_access` is documentation proof only and remains legally blocked until explicit human legal review.
